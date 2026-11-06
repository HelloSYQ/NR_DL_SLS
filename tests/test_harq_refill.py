"""Multi-codeword HARQ (engine/link.py retransmission, FullBufferConfig
harq_refill) and the rank-adaptation options of the codeword-mapping study
(CSIProcessor ri_offsets / ri_sic_propagation, FullBufferConfig ri_olla)."""

import dataclasses

import numpy as np
import pytest

from nrsls.engine.fullbuffer import run_full_buffer_drop
from nrsls.engine.link import new_txs, retransmission, tb_precoder
from nrsls.mac.link_adaptation import LinkAdaptation
from nrsls.phy.csi import CSIProcessor

from test_cw_mapping import _imbalanced_channel, _report, _same, _small

RB_PER_RBG = np.array([4, 4])


def _four_codewords(tx_id=3):
    rep, sinr_sb, la = _report(_imbalanced_channel(gains_db=(34, 32, 30, 28)), 4)
    assert rep.rank == 4
    tbs = new_txs(la, 0, 0, rep, sinr_sb, np.array([0, 1]), RB_PER_RBG, 132, 2, 0,
                  tx_id=tx_id)
    for tb in tbs:
        tb["ntx"] = 1
    return rep, sinr_sb, la, tbs


def _power(tb):
    w = tb_precoder(tb, np.ones(2, bool), np.array([0, 1]))
    return np.sum(np.abs(w) ** 2, axis=(-2, -1))


def test_no_refill_retransmits_the_failed_codewords_alone_at_full_power():
    rep, _, la, tbs = _four_codewords()
    w0 = tbs[0]["w"]
    out = retransmission(la, [tbs[1], tbs[3]], RB_PER_RBG, 132, 2, 8, refill=False)
    assert out == [tbs[1], tbs[3]]                        # no new TBs
    assert all(tb["reduced"] and tb["rank"] == 2 for tb in out)
    assert [tb["layers"] for tb in out] == [[0], [1]]     # remapped onto 2 layers
    # the remaining columns of the precoder, scaled back to full power
    assert np.allclose(out[0]["w"], w0[..., [1, 3]] * np.sqrt(2))
    assert np.allclose(_power(out[0]), 1.0)
    # a reduced transmission is never refilled, and shrinks further
    out = retransmission(la, [tbs[3]], RB_PER_RBG, 132, 2, 16, refill=True)
    assert out == [tbs[3]] and tbs[3]["rank"] == 1 and tbs[3]["layers"] == [0]
    assert np.allclose(_power(tbs[3]), 1.0)


def test_reduced_retransmission_takes_the_current_strongest_layers():
    rep, sinr_sb, la, tbs = _four_codewords()
    rep2 = dataclasses.replace(rep, rank=2, w=rep.w[..., :2] * np.sqrt(2) * 1j)
    out = retransmission(la, [tbs[2], tbs[3]], RB_PER_RBG, 132, 2, 8,
                         cur=(rep2, sinr_sb[:2]), refill=False)
    assert [tb["layers"] for tb in out] == [[0], [1]]
    assert np.allclose(out[0]["w"], rep2.w)               # rank 2 of 2: as reported
    # the current report has fewer layers than remain: keep the old columns
    _, _, _, tbs = _four_codewords()
    rep1 = dataclasses.replace(rep, rank=1, w=rep.w[..., :1] * 2)
    out = retransmission(la, tbs[1:], RB_PER_RBG, 132, 2, 8, cur=(rep1, sinr_sb[:1]),
                         refill=False)
    assert np.allclose(out[0]["w"], rep.w[..., 1:] * np.sqrt(4 / 3))


def test_refills_stop_when_the_buffer_is_empty():
    rep, _, la, tbs = _four_codewords()
    bits = tbs[0]["bits"]
    out = retransmission(la, [tbs[3]], RB_PER_RBG, 132, 2, 8, budget=bits)
    # codeword 0 takes the whole buffer, codewords 1 and 2 are disabled
    assert [tb["cw"] for tb in out] == [0, 3]
    assert out[0] is not tbs[0] and out[0]["ntx"] == 0
    assert all(tb["reduced"] and tb["rank"] == 2 for tb in out)
    assert [tb["layers"] for tb in out] == [[0], [1]]
    # an unlimited budget refills them all (the full-buffer case)
    _, _, _, tbs = _four_codewords()
    out = retransmission(la, [tbs[3]], RB_PER_RBG, 132, 2, 8, budget=None)
    assert [tb["cw"] for tb in out] == [0, 1, 2, 3]
    assert not any(tb.get("reduced") for tb in out) and out[3]["rank"] == 4


@pytest.mark.parametrize("traffic", ["full_buffer", "ftp3"])
def test_harq_refill_leaves_one_codeword_alone(traffic):
    kw = dict(traffic="ftp3", ftp_file_bytes=0.02e6, ftp_rate_per_ue=10.0) \
        if traffic == "ftp3" else {}
    cfg, fb = _small(codebook="svd", harq_adaptive=True, **kw)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(5))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, harq_refill="always"),
                             np.random.default_rng(5))
    assert _same(a, b)


def test_fresh_refill_runs_and_is_checked():
    cfg, fb = _small(codebook="svd_sb", cw_mapping="alt3", receiver="sic",
                     harq_adaptive=True, traffic="ftp3", ftp_file_bytes=0.02e6,
                     ftp_rate_per_ue=10.0)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(5))
    assert r.cell_se > 0 and r.files_counted > 0
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, harq_refill="never"),
                             np.random.default_rng(5))


# --- rank adaptation --------------------------------------------------------
def test_offset_table_shapes():
    la = LinkAdaptation(2)
    la.update(1, False)
    assert np.array_equal(la.offset_table(1), np.full((5, 1), 0.5))
    la = LinkAdaptation(2, n_cw=4)
    la.update(0, False, cw=2)
    t = la.offset_table(0)
    assert t.shape == (5, 4) and np.all(t[:, 2] == 0.5) and np.count_nonzero(t) == 5
    la = LinkAdaptation(2, n_cw=2, per_rank=True)
    la.update(0, False, cw=1, tx_rank=3)
    t = la.offset_table(0)
    assert t.shape == (5, 2) and t[3, 1] == 0.5 and np.count_nonzero(t) == 1


def test_ri_offsets_steer_the_rank_but_not_the_cqis():
    hw = _imbalanced_channel(gains_db=(30.0, 28.0, 26.0, 24.0))
    sb = np.zeros(8, int)
    proc = CSIProcessor(8, 2, codebook="svd", max_codewords=4)
    base = proc.select(hw, sb, 4, 0)
    assert base.rank == 4
    zero = proc.select(hw, sb, 4, 0, np.zeros((5, 4)))
    assert zero.rank == base.rank and zero.cqi_cw_wb == base.cqi_cw_wb
    # a large OLLA back-off on rank 4 moves the rank down; the reported
    # CQIs stay those of the channel
    off = np.zeros((5, 4))
    off[4] = 12.0
    low = proc.select(hw, sb, 4, 0, off)
    assert low.rank < 4
    _, _, sinr, _ = proc._precoder(hw, sb, low.rank)
    assert low.cqi_cw_wb[0] == proc._cqi(sinr[:, [0]], 1, 8 * 4)
    # one codeword: the offsets of codeword 0
    one = CSIProcessor(8, 2, codebook="svd")
    off1 = np.zeros((5, 1))
    off1[one.select(hw, sb, 4, 0).rank] = 12.0
    assert one.select(hw, sb, 4, 0, off1).rank != one.select(hw, sb, 4, 0).rank


def test_ri_sic_propagation_discounts_later_codewords():
    hw = _imbalanced_channel(gains_db=(30.0, 28.0, 26.0, 24.0))
    sb = np.zeros(8, int)
    plain = CSIProcessor(8, 2, codebook="svd", max_codewords=4, sic=True)
    aware = CSIProcessor(8, 2, codebook="svd", max_codewords=4, sic=True,
                         ri_sic_propagation=True)
    _, _, sinr, _ = plain._precoder(hw, sb, 4)
    sinr_a = aware._layer_sinr(hw @ plain._precoder(hw, sb, 4)[0], 4)
    _, cqi, m_plain = plain._wideband_cqi(sinr, 4, 32)
    _, cqi_a, m_aware = aware._wideband_cqi(sinr_a, 4, 32)
    assert cqi == cqi_a                                    # same CQIs reported
    from nrdlsim import mcs_tables
    se = [mcs_tables.get_cqi(q, plain.cqi_table)[2] for q in cqi]
    assert m_plain == pytest.approx(sum(se))
    assert m_aware == pytest.approx(sum(0.9 ** k * s for k, s in enumerate(se)))
    # without SIC the option does nothing
    irc = CSIProcessor(8, 2, codebook="svd", max_codewords=4, ri_sic_propagation=True)
    assert irc._wideband_cqi(sinr, 4, 32)[2] == pytest.approx(m_plain)


def test_ri_olla_runs_and_is_su_only():
    cfg, fb = _small(codebook="svd_sb", cw_mapping="alt3", receiver="sic",
                     olla_per_rank=True, ri_olla=True, ri_sic_propagation=True)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(6))
    assert r.cell_se > 0 and sum(r.rank_hist) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, mu_mimo=True, cw_mapping="alt1",
                                                      receiver="irc", olla_per_rank=False),
                             np.random.default_rng(6))
