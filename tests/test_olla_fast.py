"""OLLA fast start (LinkAdaptation fast_gain / fast_samples / fast_min_cw,
FullBufferConfig olla_fast_*): the first ACK/NACKs of a loop move it faster,
with the same up/down ratio and so the same BLER target."""

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


@pytest.mark.parametrize("kw", [{"olla_fast_gain": 0.0}, {"olla_fast_samples": -1},
                                {"olla_fast_min_cw": -1}])
def test_fast_start_options_checked(kw):
    cfg, fb = _ftp1(rate_per_cell=10.0)
    with pytest.raises(ValueError):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, **kw), np.random.default_rng(0))
