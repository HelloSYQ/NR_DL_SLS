"""FTP model 1 (FullBufferConfig.traffic='ftp1') and the twisted LTE
codeword-to-layer mapping (cw_mapping='lte_twisted')."""

import dataclasses

import numpy as np
import pytest

from nrsls.engine.fullbuffer import run_full_buffer_drop
from nrsls.mac.link_adaptation import LinkAdaptation
from nrsls.phy.csi import CSIProcessor, cw_layer_groups

from test_cw_mapping import _imbalanced_channel
from test_ftp import _small


def _ftp1(rate_per_cell, **kw):
    cfg, fb = _small(ftp_rate_per_ue=0.0, **kw)
    return cfg, dataclasses.replace(fb, traffic="ftp1", ftp1_rate_per_cell=rate_per_cell,
                                    warmup_slots=0)


# --- twisted LTE mapping -----------------------------------------------------
def test_twisted_groups_differ_from_lte_only_at_rank_four():
    for rank in (1, 2, 3):
        assert cw_layer_groups(rank, 2, "lte_twisted") == cw_layer_groups(rank, 2)
    assert cw_layer_groups(1, 2, "lte_twisted") == [[0]]
    assert cw_layer_groups(2, 2, "lte_twisted") == [[0], [1]]
    assert cw_layer_groups(3, 2, "lte_twisted") == [[0], [1, 2]]
    assert cw_layer_groups(4, 2) == [[0, 1], [2, 3]]                       # LTE
    assert cw_layer_groups(4, 2, "lte_twisted") == [[0], [1, 2, 3]]        # twisted
    assert cw_layer_groups(4, 2, "alt2t") == [[0], [1, 2, 3]]


def test_twisted_report_puts_the_strongest_layer_alone():
    hw = _imbalanced_channel(gains_db=(34.0, 28.0, 24.0, 20.0))
    sb = np.zeros(8, int)
    proc = CSIProcessor(8, 2, codebook="svd", max_codewords=2, cw_mapping="lte_twisted",
                        max_rank=4)
    # the rank-4 report of the twisted mapping, whatever rank wins overall
    _, _, sinr, _ = proc._precoder(hw, sb, 4)
    groups, cqi, _ = proc._wideband_cqi(sinr, 4, 32)
    assert groups == [[0], [1, 2, 3]]
    # SVD orders the layers by singular value: layer 0 is the strongest
    assert np.all(sinr[:, 0] >= sinr[:, 1:].max(axis=1))
    assert cqi[0] == proc._cqi(sinr[:, [0]], 1, 32)
    assert cqi[1] == proc._cqi(sinr[:, [1, 2, 3]], 3, 32)
    assert cqi[0] > cqi[1]
    rep = proc.select(hw, sb, 4, 0)
    if rep.rank == 4:
        assert rep.groups == ((0,), (1, 2, 3))


def test_twisted_mapping_runs_in_the_system():
    cfg, fb = _small(ftp_rate_per_ue=10.0, cw_mapping="lte_twisted")
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(4))
    assert r.files_counted > 0 and 1 <= r.mean_codewords <= 2
    assert len(r.bler_first_cw) <= 2


# --- FTP model 1 -------------------------------------------------------------
def test_link_adaptation_reset():
    la = LinkAdaptation(3, n_cw=2, per_rank=True)
    la.update(1, False, cw=1, tx_rank=3)
    la.update(2, False, cw=0, tx_rank=2)
    la.reset(1)
    assert np.all(la.offset[1] == 0) and la.offset[2, 2, 0] == pytest.approx(0.5)
    la1 = LinkAdaptation(2)
    la1.update(0, False)
    la1.reset(0)
    assert la1.offset[0] == 0


def test_ftp1_users_arrive_download_and_leave():
    cfg, fb = _ftp1(rate_per_cell=60.0)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(1))
    assert r.files_counted > 0
    assert r.file_upt_bps.size + r.file_upt_open_bps.size == r.files_counted
    assert (r.file_upt_bps > 0).all() and 0 < r.resource_utilization <= 1
    # one file per UT: the UTs with data never exceed the pool
    assert 0 < r.mean_active_ues <= cfg.ue_per_cell
    assert r.arrivals_blocked == 0
    # no arrivals, no traffic
    cfg0, fb0 = _ftp1(rate_per_cell=0.0)
    r0 = run_full_buffer_drop(cfg0, fb0, np.random.default_rng(1))
    assert r0.files_counted == 0 and r0.resource_utilization == 0


def test_ftp1_same_arrivals_for_every_scheme_and_load_raises_utilisation():
    cfg, fb = _ftp1(rate_per_cell=60.0)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, cw_mapping="per_layer"),
                             np.random.default_rng(3))
    assert a.files_counted == b.files_counted > 0
    hi = run_full_buffer_drop(cfg, dataclasses.replace(fb, ftp1_rate_per_cell=240.0),
                              np.random.default_rng(3))
    assert hi.resource_utilization > a.resource_utilization
    assert hi.mean_active_ues > a.mean_active_ues


def test_ftp1_small_pool_queues_arrivals():
    # a pool of 1 UT per cell under heavy load: arrivals that find no idle UT
    # queue behind one, and the run still completes
    cfg, fb = _ftp1(rate_per_cell=400.0)
    cfg = dataclasses.replace(cfg, ue_per_cell=1)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    assert r.arrivals_blocked > 0 and r.files_counted > 0
    assert r.mean_active_ues <= 1.0 + 1e-9


def test_ftp1_is_su_only_and_checked():
    cfg, fb = _ftp1(rate_per_cell=10.0)
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, traffic="ftp2"),
                             np.random.default_rng(0))
