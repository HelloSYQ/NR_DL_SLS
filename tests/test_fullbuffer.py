"""Phase 3: full-buffer SU-MIMO drop (small configuration)."""

import numpy as np

from nrsls.config.scenario import get_preset
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop


def _small(**kw):
    fb = FullBufferConfig(n_slots=40, warmup_slots=20, k_interferers=2,
                          channel_update_slots=10, csi_period_slots=10,
                          csi_delay_slots=4, **kw)
    return get_preset("rp-urllc-4g", ue_per_cell=1), fb


def test_full_buffer_runs_and_is_reproducible():
    cfg, fb = _small()
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    b = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    assert a.ue_se.shape == (57,)
    assert np.all(a.ue_se >= 0) and a.cell_se > 0
    assert np.allclose(a.ue_se, b.ue_se)
    assert 1 <= a.mean_rank <= 4
    assert 0 <= a.bler_first <= 0.5
    # a cell's UT throughput cannot exceed the carrier's peak rate
    peak = 4 * 7.4 * 1.0                                   # ~rank x 256QAM SE
    assert np.all(a.ue_se < peak)


def test_svd_precoding_is_not_worse_than_type1():
    cfg, fb = _small()
    t1 = run_full_buffer_drop(cfg, fb, np.random.default_rng(5))
    cfg, fb = _small(codebook="svd")
    sv = run_full_buffer_drop(cfg, fb, np.random.default_rng(5))
    assert sv.cell_se > 0.8 * t1.cell_se


def test_etype2_runs_in_the_system_loop():
    import dataclasses
    cfg, fb = _small(codebook="etype2", etype2_combo=4)
    # eType-II needs >= 4 ports: 8-port (4, 1) array instead of 2 ports
    cfg = dataclasses.replace(cfg, bs_antenna=dataclasses.replace(
        cfg.bs_antenna, N=4, Np=4))
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(6))
    assert r.cell_se > 0 and r.mean_pmi_bits > 20
