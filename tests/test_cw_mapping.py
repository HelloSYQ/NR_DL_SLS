"""Codeword-to-layer mapping (WP3): per-codeword CQI and RI, OLLA per
codeword, one TB per codeword and per-codeword HARQ."""

import dataclasses

import numpy as np
import pytest

from nrsls.config.scenario import UEAntenna, get_preset
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop
from nrsls.engine.link import harq_units, new_txs, retransmission
from nrsls.mac.link_adaptation import LinkAdaptation
from nrsls.phy.csi import CSIProcessor


def _imbalanced_channel(f=8, gains_db=(30.0, 24.0, 16.0, 8.0), s=32, seed=0):
    """Whitened channel (F, 4, S) with four orthogonal eigenmodes of the
    given power, the same on every frequency point."""
    rng = np.random.default_rng(seed)
    u, _ = np.linalg.qr(rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4)))
    v, _ = np.linalg.qr(rng.normal(size=(s, 4)) + 1j * rng.normal(size=(s, 4)))
    h = u @ np.diag(10 ** (np.array(gains_db) / 20)) @ v.conj().T
    return np.tile(h[None], (f, 1, 1))


def test_one_codeword_report_is_unchanged_and_has_codeword_fields():
    hw = _imbalanced_channel()
    sb = np.repeat(np.arange(2), 4)
    rep = CSIProcessor(8, 2, codebook="svd").select(hw, sb, 4, 0)
    assert rep.groups == (tuple(range(rep.rank)),)
    assert rep.cqi_cw_wb == (rep.cqi_wb,)
    assert np.array_equal(rep.cqi_cw_sb, rep.cqi_sb[None])


def test_per_codeword_cqi_follows_its_own_layers():
    hw = _imbalanced_channel()
    sb = np.repeat(np.arange(2), 4)
    proc = CSIProcessor(8, 2, codebook="svd", max_codewords=4)
    rep = proc.select(hw, sb, 4, 0)
    assert len(rep.groups) == rep.rank and all(len(g) == 1 for g in rep.groups)
    # strongest layer first: the codewords' CQIs fall with the eigenmodes
    assert list(rep.cqi_cw_wb) == sorted(rep.cqi_cw_wb, reverse=True)
    assert rep.cqi_cw_wb[0] > rep.cqi_cw_wb[-1]
    assert rep.cqi_wb == rep.cqi_cw_wb[0] and np.array_equal(rep.cqi_sb, rep.cqi_cw_sb[0])
    assert rep.cqi_cw_sb.shape == (rep.rank, 2)
    # each codeword's CQI is the CQI of its layers alone
    _, _, sinr, _ = proc._precoder(hw, sb, rep.rank)
    for g, q in zip(rep.groups, rep.cqi_cw_wb):
        assert q == proc._cqi(sinr[:, list(g)], len(g), 8 * 4)


def test_codeword_aware_rank_is_at_least_the_single_codeword_rank():
    # one codeword per layer can afford the weak layers that would drag
    # down a single codeword's MCS
    hw = _imbalanced_channel(gains_db=(30.0, 28.0, 12.0, 2.0))
    sb = np.zeros(8, int)
    r1 = CSIProcessor(8, 2, codebook="svd", max_codewords=1).select(hw, sb, 4, 0)
    r4 = CSIProcessor(8, 2, codebook="svd", max_codewords=4).select(hw, sb, 4, 0)
    assert r4.rank >= r1.rank


def test_olla_loops_per_codeword_and_rank():
    la = LinkAdaptation(2)
    assert la.offset.shape == (2,)                     # one loop per UT
    la = LinkAdaptation(2, n_cw=4)
    la.update(0, False, cw=2)
    assert la.offset[0, 0, 2] == pytest.approx(0.5) and np.count_nonzero(la.offset) == 1
    la = LinkAdaptation(2, n_cw=2, per_rank=True)
    la.update(1, False, cw=1, tx_rank=3)
    la.update(1, True, cw=1, tx_rank=2)
    assert la.offset[1, 3, 1] == pytest.approx(0.5)
    assert la.offset[1, 2, 1] < 0 and la.offset[1, 3, 0] == 0
    with pytest.raises(ValueError):
        la.update(0, True, cw=0)                       # per-rank needs the rank
    # a backed-off loop lowers that codeword's MCS only
    la = LinkAdaptation(1, n_cw=2)
    for _ in range(10):
        la.update(0, False, cw=1)
    s = np.full(4, 15.0)
    assert la.select_mcs(0, s, 1, 20, cw=1) < la.select_mcs(0, s, 1, 20, cw=0)


def _report(hw, max_cw):
    """Report on two sub-bands (= RBGs of 4 RB) and its sub-band SINRs."""
    proc = CSIProcessor(8, 2, codebook="svd", max_codewords=max_cw)
    rep = proc.select(hw, np.repeat(np.arange(2), hw.shape[0] // 2), 1, 0)
    la = LinkAdaptation(1, n_cw=max_cw)
    sinr_sb = np.array([la.cqi_sinr_db(q, len(g), 4)
                        for q, g in zip(rep.cqi_cw_sb, rep.groups)])
    return rep, sinr_sb, la


def test_new_transmission_has_one_tb_per_codeword():
    rep, sinr_sb, la = _report(_imbalanced_channel(), 2)
    rb_per_rbg = np.array([4, 4])
    tbs = new_txs(la, 0, 0, rep, sinr_sb, np.array([0, 1]), rb_per_rbg, 132, 2, 0, tx_id=7)
    assert [tb["cw"] for tb in tbs] == list(range(len(rep.groups)))
    assert [tb["layers"] for tb in tbs] == [list(g) for g in rep.groups]
    assert all(tb["tx"] == 7 and tb["rank"] == rep.rank and tb["w"] is rep.w for tb in tbs)
    assert [tb["lead"] for tb in tbs] == [True] + [False] * (len(tbs) - 1)
    # the stronger codeword gets the higher MCS
    assert tbs[0]["info"].index >= tbs[-1]["info"].index
    # one codeword: the single-TB path
    rep1, s1, la1 = _report(_imbalanced_channel(), 1)
    one = new_txs(la1, 0, 0, rep1, s1[0], np.array([0, 1]), rb_per_rbg, 132, 2, 0, tx_id=0)
    assert len(one) == 1 and "tx" not in one[0]


def test_retransmission_resends_failed_codewords_and_refills_the_others():
    rep, sinr_sb, la = _report(_imbalanced_channel(gains_db=(34, 32, 30, 28)), 4)
    assert rep.rank == 4
    rb_per_rbg = np.array([4, 4])
    tbs = new_txs(la, 0, 0, rep, sinr_sb, np.array([0, 1]), rb_per_rbg, 132, 2, 0, tx_id=3)
    for tb in tbs:
        tb["ntx"] = 1
    failed = [tbs[1], tbs[3]]
    assert harq_units(failed + [{"ue": 5}]) == [failed, [{"ue": 5}]]
    out = retransmission(la, failed, rb_per_rbg, 132, 2, slot=8)
    assert [tb["cw"] for tb in out] == list(range(len(tbs)))
    assert out[1] is tbs[1] and out[3] is tbs[3]               # same TBs again
    for k in (0, 2):                                          # refills: new TBs
        assert out[k] is not tbs[k] and out[k]["ntx"] == 0 and out[k]["due"] == 8
        assert out[k]["tx"] == 3 and out[k]["layers"] == tbs[k]["layers"]
        assert out[k]["info"].index == tbs[k]["info"].index   # same CQI and OLLA
    assert all(np.array_equal(tb["rbgs"], tbs[0]["rbgs"]) for tb in out)
    # adaptive: the current report's precoder for all, if the rank matches
    rep2 = dataclasses.replace(rep, w=rep.w * 1j)
    out = retransmission(la, [tbs[1]], rb_per_rbg, 132, 2, 8, cur=(rep2, sinr_sb - 6))
    assert all(tb["w"] is rep2.w for tb in out)
    assert out[0]["info"].index < tbs[0]["info"].index        # refill on the new CQI
    rep3 = dataclasses.replace(rep, rank=rep.rank - 1, w=rep.w[:, :-1])
    tb = dict(tbs[2], ntx=1)
    out = retransmission(la, [tb], rb_per_rbg, 132, 2, 8, cur=(rep3, sinr_sb))
    assert out[2]["w"] is not rep3.w                          # rank differs: keep


def _small(**kw):
    fb = FullBufferConfig(n_slots=30, warmup_slots=10, k_interferers=2, rb_step=4,
                          channel_update_slots=5, csi_period_slots=5, csi_delay_slots=2,
                          **kw)
    cfg = get_preset("rp-urllc-4g", ue_per_cell=1)
    cfg = dataclasses.replace(cfg, bs_antenna=dataclasses.replace(cfg.bs_antenna, N=4, Np=4),
                              ue_antenna=UEAntenna(M=1, N=2, P=2))
    return cfg, fb


def _same(a, b):
    return all(np.array_equal(np.asarray(getattr(a, f.name)), np.asarray(getattr(b, f.name)))
               for f in dataclasses.fields(a))


def test_one_codeword_per_layer_at_rank_one_is_the_single_codeword_system():
    # with rank <= 1 every mapping has one codeword: the multi-codeword
    # path (per-codeword SINRs, TBs, OLLA, HARQ units) must reproduce NR
    cfg, fb = _small(codebook="svd", max_rank=1)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(4))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, cw_mapping="alt3"),
                             np.random.default_rng(4))
    assert _same(a, b)
    # up to rank 2, Alt 2 and Alt 3 split the layers the same way
    cfg, fb = _small(codebook="svd", max_rank=2, cw_mapping="alt2")
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(4))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, cw_mapping="alt3"),
                             np.random.default_rng(4))
    assert _same(a, b)


@pytest.mark.parametrize("adaptive", [False, True])
def test_multi_codeword_system_runs(adaptive):
    cfg, fb = _small(codebook="svd_rb", cw_mapping="alt3", olla_per_rank=True,
                     harq_adaptive=adaptive)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    assert r.cell_se > 0 and 1 < r.mean_codewords <= 4
    assert r.mean_codewords == pytest.approx(r.mean_rank)     # one CW per layer
    assert sum(r.rank_hist) == pytest.approx(1.0)
    assert len(r.bler_first_cw) >= 2 and all(0 <= b <= 0.6 for b in r.bler_first_cw)


def test_multi_codeword_mappings_are_su_only():
    cfg, fb = _small(mu_mimo=True, max_rank=2, cw_mapping="alt2")
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, fb, np.random.default_rng(0))
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, mu_mimo=False, cw_mapping="alt5"),
                             np.random.default_rng(0))


# --- codeword-level SIC and ideal link adaptation (references) -------------
def _selective_channel(f=8, s=32, seed=1):
    """Frequency-selective whitened channel (F, 4, S): a wideband precoder
    leaves inter-layer interference, which SIC can remove."""
    rng = np.random.default_rng(seed)
    return 3 * (rng.normal(size=(f, 4, s)) + 1j * rng.normal(size=(f, 4, s)))


def test_sic_layer_sinr_cancels_decoded_layers():
    from nrsls.engine.link import sic_layer_sinr
    from nrsls.phy.sinr import mmse_sinr
    g = _selective_channel()[:, :, :3]                       # (F, 4, 3)
    assert np.array_equal(sic_layer_sinr(g, [1, 2], []), mmse_sinr(g)[:, [1, 2]])
    # everything else cancelled: matched filter, |g_l|^2
    assert np.allclose(sic_layer_sinr(g, [1], [0, 2])[:, 0],
                       np.sum(np.abs(g[:, :, 1]) ** 2, axis=1))
    assert np.all(sic_layer_sinr(g, [2], [0]) >= mmse_sinr(g)[:, [2]] - 1e-9)


def test_sic_report_cqis_assume_earlier_codewords_cancelled():
    hw = _selective_channel()
    sb = np.repeat(np.arange(2), 4)
    # one codeword: SIC changes nothing
    a = CSIProcessor(8, 2, codebook="svd").select(hw, sb, 4, 0)
    b = CSIProcessor(8, 2, codebook="svd", sic=True).select(hw, sb, 4, 0)
    assert (a.rank, a.cqi_wb) == (b.rank, b.cqi_wb) and np.array_equal(a.cqi_sb, b.cqi_sb)
    from nrsls.phy.sinr import mmse_sinr
    for max_cw in (2, 4):                                    # LTE, one per layer
        irc = CSIProcessor(8, 2, codebook="svd", max_codewords=max_cw)
        sic = CSIProcessor(8, 2, codebook="svd", max_codewords=max_cw, sic=True)
        w, _, s_irc, _ = irc._precoder(hw, sb, 4)
        _, _, s_sic, _ = sic._precoder(hw, sb, 4)
        g = hw @ w
        groups = [[0, 1], [2, 3]] if max_cw == 2 else [[0], [1], [2], [3]]
        for grp in groups:                                   # after groups before
            assert np.allclose(s_sic[:, grp], mmse_sinr(g[..., grp[0]:])[:, :len(grp)])
        assert np.array_equal(s_sic[:, groups[0]], s_irc[:, groups[0]])
        assert np.all(s_sic >= s_irc - 1e-9) and np.any(s_sic > s_irc * 1.01)
        r_irc, r_sic = irc.select(hw, sb, 4, 0), sic.select(hw, sb, 4, 0)
        if r_irc.rank == r_sic.rank:
            assert all(q2 >= q1 for q1, q2 in zip(r_irc.cqi_cw_wb, r_sic.cqi_cw_wb))


def test_ideal_mcs_is_the_highest_meeting_the_target():
    from nrdlsim import mcs_tables
    from nrdlsim import tbs as tbs_mod
    from nrdlsim.link_abstraction import bler_from_effective_sinr, effective_sinr_miesm
    from nrsls.engine.link import ideal_mcs
    rb_per_rbg, nrb = np.array([4, 4]), np.full(4, 2)
    for snr_db in (-3.0, 8.0, 17.0, 40.0):
        sinr = np.full((4, 2), 10 ** (snr_db / 10))          # 4 points x 2 layers
        tb = {"rbgs": np.array([0, 1])}
        ideal_mcs(tb, sinr, nrb, rb_per_rbg, 132, 2, 0.1)
        re = np.repeat(sinr, nrb, axis=0)

        def bler(i):
            info = mcs_tables.get_mcs(i, 2)
            bits = tbs_mod.compute_tbs(132, 8, info.modulation_order,
                                       info.target_code_rate, 2)
            return bler_from_effective_sinr(effective_sinr_miesm(re, info.modulation_order),
                                            info.modulation_order, info.target_code_rate,
                                            bits), bits
        i = tb["info"].index
        assert tb["bits"] == bler(i)[1]
        if i > 0:
            assert bler(i)[0] <= 0.1 + 1e-6
        if i < mcs_tables.num_mcs(2) - 1:
            assert bler(i + 1)[0] > 0.1


def test_sic_with_one_codeword_is_the_irc_system():
    cfg, fb = _small(codebook="svd", cw_mapping="nr")
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, receiver="sic"),
                             np.random.default_rng(3))
    assert _same(a, b)
    # rank 1: the SIC decoding path of the per-layer mapping reproduces NR
    cfg, fb = _small(codebook="svd", max_rank=1)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(4))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, cw_mapping="per_layer",
                                                      receiver="sic"),
                             np.random.default_rng(4))
    assert _same(a, b)


@pytest.mark.parametrize("mapping,receiver", [("lte", "sic"), ("per_layer", "sic"),
                                              ("nr", "irc"), ("per_layer", "irc")])
def test_sic_and_ideal_la_systems_run(mapping, receiver):
    cfg, fb = _small(codebook="svd_rb", cw_mapping=mapping, receiver=receiver,
                     harq_adaptive=True)
    olla = run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    ideal = run_full_buffer_drop(cfg, dataclasses.replace(fb, ideal_la=True),
                                 np.random.default_rng(2))
    for r in (olla, ideal):
        assert r.cell_se > 0 and 1 <= r.mean_codewords <= 4
    # the MCS meets the target on the actual SINR: BLER at most ~target
    assert ideal.bler_first <= 0.15


def test_cw_mapping_names_and_reference_options():
    from nrsls.engine.fullbuffer import CW_MAPPINGS
    assert [CW_MAPPINGS[k] for k in ("nr", "lte", "per_layer")] == \
        [CW_MAPPINGS[k] for k in ("alt1", "alt2", "alt3")]
    cfg, fb = _small(receiver="mlse")
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, fb, np.random.default_rng(0))
    for kw in ({"receiver": "sic"}, {"ideal_la": True}):
        cfg, fb = _small(mu_mimo=True, max_rank=2, **kw)
        with pytest.raises(ValueError):
            run_full_buffer_drop(cfg, fb, np.random.default_rng(0))


def test_sic_ideal_la_does_not_know_whether_earlier_codewords_decode(monkeypatch):
    """With SIC, the ideal MCS of a codeword is chosen on its SINR with all
    earlier codewords cancelled, even when one of them then fails; the
    decoder uses the actual cancellation (error propagation kept)."""
    from nrsls.engine import fullbuffer as fbm
    calls, plans = {}, []
    real_sic, real_ideal = fbm.sic_layer_sinr, fbm.ideal_mcs

    def sic(g, layers, cancelled):
        out = real_sic(g, layers, cancelled)
        calls[id(out)] = (list(layers), sorted(cancelled))
        return out

    def ideal(tb, sinr, *a):
        plans.append((list(tb["layers"]), calls.get(id(sinr))))
        return real_ideal(tb, sinr, *a)

    monkeypatch.setattr(fbm, "sic_layer_sinr", sic)
    monkeypatch.setattr(fbm, "ideal_mcs", ideal)
    monkeypatch.setattr(fbm, "decode_tb", lambda *a, **k: False)    # nothing decodes
    cfg, fb = _small(codebook="svd_rb", cw_mapping="per_layer", receiver="sic",
                     ideal_la=True, harq_adaptive=True)
    run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    later = [(layers, c) for layers, c in plans if layers[0] > 0]
    assert later
    for layers, (sinr_layers, cancelled) in later:
        assert sinr_layers == layers and cancelled == list(range(layers[0]))
