"""1024QAM (MCS / CQI table 4, EVM ceiling) and the 50 MHz study set-up."""

import os
import sys

import numpy as np
import pytest

from nrdlsim import mcs_tables

from nrsls.config.scenario import get_preset
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop
from nrsls.mac import mcs_table4
from nrsls.mac.link_adaptation import LinkAdaptation, mcs_required_sinr_db
from nrsls.phy.csi import CSIProcessor
from nrsls.phy.sinr import evm_limited

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))


def test_mcs_table_4_is_the_rel17_table():
    n = mcs_tables.num_mcs(4)
    assert n == 27                                   # indices 0-26; 27-31 are reserved
    rows = [mcs_tables.get_mcs(i, 4) for i in range(n)]
    assert [r.modulation_order for r in rows] == [2] * 3 + [4] * 3 + [6] * 9 + [8] * 8 + [10] * 4
    # the 1024QAM rows, R x 1024 and spectral efficiency (RAN1 #104-e)
    top = [(r.target_code_rate * 1024, round(r.spectral_efficiency, 4)) for r in rows[23:]]
    assert top == [(805.5, 7.8662), (853, 8.3301), (900.5, 8.7939), (948, 9.2578)]
    # the rest are rows of the 256QAM table, in its order, with the same 64QAM
    # and 256QAM rows
    t2 = [(mcs_tables.get_mcs(i, 2).modulation_order, mcs_tables.get_mcs(i, 2).target_code_rate)
          for i in range(mcs_tables.num_mcs(2))]
    low = [(r.modulation_order, r.target_code_rate) for r in rows[:23]]
    assert [x for x in t2 if x in low] == low
    assert [x for x in low if x[0] >= 6] == [x for x in t2 if x[0] >= 6]
    se = [r.spectral_efficiency for r in rows]
    assert all(b > a for a, b in zip(se, se[1:]))
    assert mcs_tables.get_mcs(26, 4).modulation_name == "1024QAM"
    with pytest.raises(ValueError):
        mcs_tables.get_mcs(27, 4)


def test_cqi_table_4_and_registration():
    assert mcs_tables.MCS_TO_CQI_TABLE[4] == 4
    cqi = [mcs_tables.get_cqi(i, 4) for i in range(16)]
    assert [c[0] for c in cqi[1:]] == [2] * 3 + [4] * 2 + [6] * 4 + [8] * 4 + [10] * 2
    assert cqi[14][2] == 8.3301 and cqi[15][2] == 9.2578
    for qm, rate, eff in cqi[1:]:
        assert abs(qm * rate - eff) < 1e-3
    # every CQI's (Qm, R) is a row of the MCS table
    mcs = {(mcs_tables.get_mcs(i, 4).modulation_order, mcs_tables.get_mcs(i, 4).target_code_rate)
           for i in range(27)}
    assert all((qm, rate) in mcs for qm, rate, _ in cqi[2:])
    mcs_table4.register()                            # idempotent
    assert mcs_tables.num_mcs(4) == 27 and mcs_tables.num_mcs(2) == 28


def test_evm_limits_the_sinr():
    s = np.array([1e-2, 1.0, 1e2, 1e3, 1e6])
    assert evm_limited(s, 0.0) is s
    lim = evm_limited(s, 2.5)
    assert np.all(lim < s) and np.all(lim < 1 / 0.025 ** 2)
    assert 10 * np.log10(lim[-1]) == pytest.approx(32.04, abs=0.01)   # the ceiling
    assert lim[1] == pytest.approx(1.0, rel=1e-3)                     # low SINRs untouched
    assert 10 * np.log10(evm_limited(np.array([1e9]), 3.5)[0]) == pytest.approx(29.12, abs=0.01)


def test_link_adaptation_reaches_1024qam_only_at_high_sinr():
    la4, la2 = LinkAdaptation(1, mcs_table=4), LinkAdaptation(1, mcs_table=2)
    qm = lambda la, s: mcs_tables.get_mcs(la.select_mcs(0, np.array([s]), 1, 52),
                                          la.mcs_table).modulation_order
    assert qm(la4, 45.0) == 10 and la4.select_mcs(0, np.array([45.0]), 1, 52) == 26
    assert qm(la4, 24.0) <= 8 and qm(la2, 45.0) == 8
    # 1024QAM starts above 256QAM's highest rate and its own highest rate
    # needs more than the 32 dB an EVM of 2.5 % leaves
    req4 = mcs_required_sinr_db(4, 1, 0.1, 111, 52)
    req2 = mcs_required_sinr_db(2, 1, 0.1, 111, 52)
    assert req4[23] > req2[27] and 26 < req4[23] < 30
    assert req4[26] > 32.04 > req4[25]
    assert np.all(np.diff(req4) > 0)


def test_csi_with_1024qam_and_evm():
    rng = np.random.default_rng(0)
    h = (rng.normal(size=(8, 4, 8)) + 1j * rng.normal(size=(8, 4, 8))) * 300.0
    sb = np.repeat(np.arange(2), 4)
    kw = dict(codebook="svd", max_rank=1, n_re_per_rb=111)
    rep = lambda **k: CSIProcessor(4, 1, **kw, **k).select(h, sb, 2, 0)
    assert rep(mcs_table=2).cqi_wb == 15
    assert rep(mcs_table=4).cqi_wb == 15                       # 1024QAM, rate 948/1024
    assert rep(mcs_table=4, evm_percent=2.5).cqi_wb == 14      # below the 32 dB ceiling
    assert rep(mcs_table=2, evm_percent=2.5).cqi_wb == 15      # 256QAM does not need more


def _small(**kw):
    fb = FullBufferConfig(n_slots=40, warmup_slots=20, k_interferers=2,
                          channel_update_slots=10, csi_period_slots=10,
                          csi_delay_slots=4, codebook="svd", **kw)
    return get_preset("rp-urllc-4g", ue_per_cell=1), fb


def test_1024qam_and_evm_run_in_the_system():
    cfg, fb = _small()
    base = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    assert len(base.modulation_share) == 5 and sum(base.modulation_share) == pytest.approx(1.0)
    assert base.modulation_share[4] == 0.0                     # no 1024QAM in table 2
    cfg, fb = _small(mcs_table=4)
    q = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    assert sum(q.modulation_share) == pytest.approx(1.0) and q.cell_se > 0
    cfg, fb = _small(mcs_table=4, evm_percent=8.0)             # a 21.9 dB ceiling
    e = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    assert e.modulation_share[4] == 0.0            # 1024QAM needs more than 27 dB
    assert 0 < e.cell_se <= q.cell_se
    with pytest.raises(ValueError):
        run_full_buffer_drop(*_small(evm_percent=-1.0), np.random.default_rng(3))


def test_study_setups_50mhz_and_1024qam():
    import cw2lm_ftp_eval as ev
    cfg = ev.scenario("50mhz-ftp1")
    assert cfg.carrier.n_size_grid == 133 and cfg.carrier.scs_khz == 30
    assert cfg.bs_tx_power_dbm == 48.0 and cfg.channel_bandwidth_hz == 50e6
    # the same power per RE as 44 dBm on the 20 MHz carrier's 52 PRB, within 0.1 dB
    psd = lambda c: c.bs_tx_power_dbm - 10 * np.log10(c.carrier.n_size_grid)
    assert abs(psd(cfg) - psd(ev.scenario("20mhz-ftp1"))) < 0.1
    fb = lambda s: ev.fb_config("svd_sb_20ms", "irc-fix-warmfast", "lte", 10.0, 1000, 0, 0, s)
    f20, f50, q20, q50 = (fb(s) for s in ("20mhz-ftp1", "50mhz-ftp1", "20mhz-ftp1-1024qam",
                                          "50mhz-ftp1-1024qam"))
    assert (f20.rbg_size, f20.mcs_table, f20.evm_percent) == (4, 2, 0.0)
    assert (f50.rbg_size, f50.mcs_table, f50.evm_percent) == (8, 2, 0.0)
    assert (q20.rbg_size, q20.mcs_table, q20.evm_percent) == (4, 4, 2.5)
    assert (q50.rbg_size, q50.mcs_table, q50.evm_percent) == (8, 4, 2.5)
    assert all(f.traffic == "ftp1" and f.csi_period_slots == 40 for f in (f50, q20, q50))
    # a 1024QAM set-up runs on its 256QAM set-up's arrival rates
    assert ev.SETUPS["20mhz-ftp1-1024qam"]["rates"] == ev.SETUPS["20mhz-ftp1"]["rates"]
    assert ev.SETUPS["50mhz-ftp1-1024qam"]["rates"] == ev.SETUPS["50mhz-ftp1"]["rates"]
    assert ev.SETUPS["50mhz-ftp1"]["rates"] != ev.SETUPS["20mhz-ftp1"]["rates"]
    assert len({s["out"] for s in ev.SETUPS.values()}) == len(ev.SETUPS)
