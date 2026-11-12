"""OLLA fast start (LinkAdaptation fast_gain / fast_samples / fast_min_cw,
FullBufferConfig olla_fast_*): the first ACK/NACKs of a loop move it faster,
with the same up/down ratio and so the same BLER target; and warm start
(warm_samples, olla_warm_samples): a new UT's loops start from the mean of
the converged loops."""

import dataclasses

import numpy as np
import pytest

from nrsls.engine.fullbuffer import run_full_buffer_drop
from nrsls.mac.link_adaptation import LinkAdaptation

from test_cw_mapping import _same
from test_ftp1_twisted import _ftp1

ACK = 0.5 * 0.1 / 0.9


def test_fast_start_scales_the_first_steps_of_each_loop():
    la = LinkAdaptation(2, n_cw=2, fast_gain=4, fast_samples=3)
    for _ in range(3):
        la.update(0, False, cw=1)
    assert la.offset[0, 0, 1] == pytest.approx(3 * 2.0)
    la.update(0, False, cw=1)                       # the 4th: the normal step
    assert la.offset[0, 0, 1] == pytest.approx(6.5)
    # the ACK step scales by the same gain: the ratio, and so the target, stay
    la.update(0, True, cw=0)
    assert la.offset[0, 0, 0] == pytest.approx(-4 * ACK)
    # every loop counts its own samples; a new UT is fast again
    la.update(1, False, cw=1)
    assert la.offset[1, 0, 1] == pytest.approx(2.0)
    la.reset(0)
    la.update(0, False, cw=1)
    assert la.offset[0, 0, 1] == pytest.approx(2.0)
    # the +-10 dB limit still holds
    big = LinkAdaptation(1, fast_gain=40, fast_samples=1)
    big.update(0, False)
    assert big.offset[0] == pytest.approx(10.0)


def test_fast_start_from_a_codeword_index_and_per_rank():
    la = LinkAdaptation(1, n_cw=4, fast_gain=4, fast_samples=5, fast_min_cw=1)
    la.update(0, False, cw=0)
    la.update(0, False, cw=3)
    assert la.offset[0, 0, 0] == pytest.approx(0.5)  # codeword 0: normal steps
    assert la.offset[0, 0, 3] == pytest.approx(2.0)
    # one codeword (NR) is codeword 0: fast_min_cw=1 leaves it alone
    nr = LinkAdaptation(1, fast_gain=4, fast_samples=5, fast_min_cw=1)
    nr.update(0, False)
    assert nr.offset[0] == pytest.approx(0.5)
    nr = LinkAdaptation(1, fast_gain=4, fast_samples=5)
    nr.update(0, False)
    assert nr.offset[0] == pytest.approx(2.0)
    # OLLA per rank: each rank's loop has its own fast start
    pr = LinkAdaptation(1, n_cw=2, per_rank=True, fast_gain=4, fast_samples=1)
    pr.update(0, False, cw=1, tx_rank=3)
    pr.update(0, False, cw=1, tx_rank=3)
    pr.update(0, False, cw=1, tx_rank=4)
    assert pr.offset[0, 3, 1] == pytest.approx(2.5)
    assert pr.offset[0, 4, 1] == pytest.approx(2.0)


def test_no_fast_start_is_the_plain_loop():
    cfg, fb = _ftp1(rate_per_cell=60.0, cw_mapping="per_layer")
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(1))
    for kw in ({"olla_fast_gain": 1.0, "olla_fast_samples": 50},
               {"olla_fast_gain": 4.0, "olla_fast_samples": 0}):
        b = run_full_buffer_drop(cfg, dataclasses.replace(fb, **kw), np.random.default_rng(1))
        assert _same(a, b)
    fast = dataclasses.replace(fb, olla_fast_gain=4.0, olla_fast_samples=20)
    assert not _same(a, run_full_buffer_drop(cfg, fast, np.random.default_rng(1)))


def test_weak_codeword_fast_start_leaves_nr_alone():
    cfg, fb = _ftp1(rate_per_cell=60.0)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(2))
    weak = dataclasses.replace(fb, olla_fast_gain=4.0, olla_fast_samples=20,
                               olla_fast_min_cw=1)
    assert _same(a, run_full_buffer_drop(cfg, weak, np.random.default_rng(2)))
    every = dataclasses.replace(weak, olla_fast_min_cw=0)
    assert not _same(a, run_full_buffer_drop(cfg, every, np.random.default_rng(2)))


def test_warm_start_takes_the_mean_of_the_converged_loops():
    la = LinkAdaptation(4, n_cw=2, warm_samples=3)
    for _ in range(3):
        la.update(0, False, cw=0)                   # 3 samples: +1.5 dB
    la.update(0, False, cw=1)                       # 1 sample: not converged
    for _ in range(4):
        la.update(1, True, cw=0)                    # 4 samples: -4 ACK steps
    la.update(2, False, cw=0)                       # 1 sample: not converged
    la.reset(3)
    assert la.offset[3, 0, 0] == pytest.approx((1.5 - 4 * ACK) / 2)
    assert la.offset[3, 0, 1] == 0.0                # no converged peer: 0 dB
    assert np.all(la.n_updates[3] == 0)
    # a returning UT does not count its own old loop
    la.reset(0)
    assert la.offset[0, 0, 0] == pytest.approx(-4 * ACK)
    # one codeword (NR)
    nr = LinkAdaptation(3, warm_samples=2)
    nr.update(0, False)
    nr.update(0, False)
    nr.update(1, False)
    nr.reset(2)
    assert nr.offset[2] == pytest.approx(1.0)
    # OLLA per rank: per rank and codeword
    pr = LinkAdaptation(3, n_cw=2, per_rank=True, warm_samples=1)
    pr.update(0, False, cw=1, tx_rank=3)
    pr.update(1, True, cw=1, tx_rank=4)
    pr.reset(2)
    assert pr.offset[2, 3, 1] == pytest.approx(0.5)
    assert pr.offset[2, 4, 1] == pytest.approx(-ACK)
    assert np.count_nonzero(pr.offset[2]) == 2
    # off: zeros, as before
    off = LinkAdaptation(2)
    off.update(0, False)
    off.reset(1)
    assert off.offset[1] == 0.0


def test_warm_start_acts_on_arrivals_only():
    # FTP model 1: every arrival starts warm, so the run changes
    cfg, fb = _ftp1(rate_per_cell=60.0, cw_mapping="per_layer")
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(3))
    warm = dataclasses.replace(fb, olla_warm_samples=5)
    b = run_full_buffer_drop(cfg, warm, np.random.default_rng(3))
    assert not _same(a, b) and b.files_counted == a.files_counted > 0
    # FTP model 3 has no arrivals of UTs: the loops are never reset
    from test_ftp import _small as _ftp3
    cfg3, fb3 = _ftp3(ftp_rate_per_ue=10.0, cw_mapping="per_layer")
    a3 = run_full_buffer_drop(cfg3, fb3, np.random.default_rng(3))
    b3 = run_full_buffer_drop(cfg3, dataclasses.replace(fb3, olla_warm_samples=5),
                              np.random.default_rng(3))
    assert _same(a3, b3)


@pytest.mark.parametrize("kw", [{"olla_fast_gain": 0.0}, {"olla_fast_samples": -1},
                                {"olla_fast_min_cw": -1}, {"olla_warm_samples": -1}])
def test_fast_start_options_checked(kw):
    cfg, fb = _ftp1(rate_per_cell=10.0)
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, **kw), np.random.default_rng(0))


def test_fair_baseline_variant_of_the_study_script():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
    import cw2lm_ftp_eval as ev
    v = "irc-fix-warmfast-pr-rtt4"
    assert ev.nr_reference(v) == v                   # NR runs with the same link adaptation
    for scheme in ("nr", "lte", "per_layer"):
        fb = ev.fb_config("svd_sb_20ms", v, scheme, 7.0, 1000, 0, 0, "20mhz-ftp1")
        assert fb.olla_per_rank and fb.harq_rtt_slots == 4 and fb.harq_refill == "fresh"
        assert (fb.olla_fast_gain, fb.olla_fast_samples, fb.olla_warm_samples) == (4.0, 20, 20)
        assert fb.receiver == "irc" and not fb.ri_olla and fb.mcs_table == 2
    base = ev.fb_config("svd_sb_20ms", "irc-fix-warmfast", "nr", 7.0, 1000, 0, 0, "20mhz-ftp1")
    assert not base.olla_per_rank and base.harq_rtt_slots == 8


def test_final_setup_of_the_study_script():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
    import cw2lm_ftp_eval as ev
    final, hand = ev.SETUPS["20mhz-ftp1-grip-hand-fair"], ev.SETUPS["20mhz-ftp1-grip-hand"]
    assert final["preset"] == hand["preset"]         # the grip and the hand loss
    sc = ev.scenario("20mhz-ftp1-grip-hand-fair")
    assert sc.ue_self_blocking and sc.hand_loss_db == ev.HAND_LOSS_DB
    # its own rates (calibrated with the fair baseline) and summary
    others = [s for k, s in ev.SETUPS.items() if k != "20mhz-ftp1-grip-hand-fair"]
    assert all(final["rates"] != s["rates"] and final["out"] != s["out"] for s in others)
