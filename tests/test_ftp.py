"""FTP model 3 traffic in the SU slot loop (FullBufferConfig.traffic='ftp3')."""

import dataclasses

import numpy as np
import pytest

from nrsls.config.scenario import UEAntenna, get_preset
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop


def _small(**kw):
    fb = FullBufferConfig(n_slots=120, warmup_slots=20, k_interferers=2, rb_step=4,
                          rbg_size=4, channel_update_slots=2, csi_period_slots=5,
                          csi_delay_slots=2, codebook="svd_sb", harq_adaptive=True,
                          traffic="ftp3", ftp_file_bytes=0.02e6, **kw)
    cfg = get_preset("rp-urllc-4g", ue_per_cell=2)
    cfg = dataclasses.replace(cfg, bs_antenna=dataclasses.replace(cfg.bs_antenna, N=4, Np=4),
                              ue_antenna=UEAntenna(M=1, N=2, P=2))
    return cfg, fb


def test_no_files_no_traffic():
    cfg, fb = _small(ftp_rate_per_ue=0.0)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(1))
    assert r.resource_utilization == 0 and r.files_counted == 0
    assert r.file_upt_bps.size == 0 and r.cell_se == 0


def test_files_complete_and_load_raises_utilisation():
    out = {}
    for rate in (5.0, 40.0):
        cfg, fb = _small(ftp_rate_per_ue=rate, ftp_drain_slots=40)
        out[rate] = run_full_buffer_drop(cfg, fb, np.random.default_rng(1))
    lo, hi = out[5.0], out[40.0]
    assert 0 < lo.resource_utilization < hi.resource_utilization <= 1
    for r in (lo, hi):
        assert r.files_counted > 0 and 0 < r.file_upt_bps.size <= r.files_counted
        assert r.file_upt_bps.size + r.file_upt_open_bps.size == r.files_counted
        assert (r.file_upt_bps > 0).all() and r.file_ue.size == r.file_upt_bps.size
    # at light load, with a drain longer than any transfer, every counted file completes
    assert lo.file_upt_bps.size == lo.files_counted
    # more load, more queueing: lower mean UPT
    assert hi.file_upt_bps.mean() < lo.file_upt_bps.mean()


def test_same_files_for_every_scheme_and_same_drop_as_full_buffer():
    cfg, fb = _small(ftp_rate_per_ue=10.0)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, cw_mapping="per_layer",
                                                      receiver="sic"),
                             np.random.default_rng(3))
    full = run_full_buffer_drop(cfg, dataclasses.replace(fb, traffic="full_buffer"),
                                np.random.default_rng(3))
    assert a.files_counted == b.files_counted > 0
    # the traffic stream is spawned, so the drop (layout, geometry) is unchanged
    assert np.array_equal(a.geometry_db, full.geometry_db)
    assert np.array_equal(a.serving_cell, full.serving_cell)


def test_ftp_options_checked():
    cfg, fb = _small(ftp_rate_per_ue=1.0)
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, traffic="ftp2"),
                             np.random.default_rng(0))
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, mu_mimo=True, harq_adaptive=False,
                                                      max_rank=2),
                             np.random.default_rng(0))


def test_file_arrival_times_allow_a_drain_afterwards():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
    import cw2lm_ftp_eval as ev
    # no warm-up, no drain: every file counts, and its arrival time is kept
    cfg, fb = _small(ftp_rate_per_ue=40.0)
    fb = dataclasses.replace(fb, warmup_slots=0)
    r = run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    t_end = fb.n_slots * cfg.carrier.slot_duration_s
    assert r.file_arrival_s.size == r.file_upt_bps.size > 0
    assert r.file_arrival_open_s.size == r.file_upt_open_bps.size
    arr = np.concatenate([r.file_arrival_s, r.file_arrival_open_s])
    assert arr.size == r.files_counted and ((0 <= arr) & (arr < t_end)).all()
    # the runner's summary-time drain keeps the files that arrived early enough
    rec = {"n_slots": fb.n_slots, "setup": "10mhz", "upt": r.file_upt_bps.tolist(),
           "upt_open": r.file_upt_open_bps.tolist(), "upt_t": r.file_arrival_s.tolist(),
           "upt_open_t": r.file_arrival_open_s.tolist()}
    slot = ev.scenario("10mhz").carrier.slot_duration_s
    done, still = ev._files(rec, drain=40)
    t_max = (fb.n_slots - 40) * slot
    assert len(done) == int(np.sum(r.file_arrival_s < t_max))
    assert len(still) == int(np.sum(r.file_arrival_open_s < t_max))
    assert ev._files(rec) == (rec["upt"], rec["upt_open"])          # no drain: as run
    # ... and summarize() applies it (the run's own drain field must not mask it)
    base = dict(rec, case="svd_sb_20ms", load="20", rate=1.0, drop=0, warmup=0, drain=0,
                seed=1, ru=0.2, served_se=1.0, bler_first=0.1, bler_first_cw=[0.1],
                mean_rank=2.0, rank_hist=[0, 1, 0, 0], retx_rbg_fraction=0.0, runtime_s=1.0)
    log = [dict(base, variant="irc-olla", scheme="nr"), dict(base, variant="irc-fix", scheme="lte")]
    e = ev.summarize(log, "10mhz", drain=40)["configurations"][0]
    assert e["variants"]["irc-olla"]["nr"]["files"] == len(done) + len(still)
    assert ev._files({k: v for k, v in rec.items() if k not in ("upt_t", "upt_open_t")},
                     drain=40) == (rec["upt"], rec["upt_open"])     # old records: as run
