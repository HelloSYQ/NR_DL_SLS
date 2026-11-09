"""Asynchronous HARQ (FullBufferConfig harq_mode='async', fullbuffer._async_rbgs):
a due retransmission keeps priority but takes the best free RBGs for the UT's
current report instead of being pinned to its own."""

import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest

from nrsls.engine.fullbuffer import _async_rbgs, run_full_buffer_drop

from test_cw_mapping import _same
from test_cw_mapping import _small as _full_buffer
from test_ftp import _small as _ftp3

SIG = [(2, 2)] * 6                       # six RBGs, two 2-RB points each


def _report(rank, sinr_sb):
    groups = tuple((k,) for k in range(len(sinr_sb))) if np.ndim(sinr_sb) == 2 else ((0,),)
    return SimpleNamespace(rank=rank, groups=groups), np.asarray(sinr_sb, float)


def test_async_rbgs_takes_the_best_free_rbgs_of_the_current_report():
    unit = [{"rbgs": np.array([0, 1]), "rank": 2}]
    sinr = [[0, 0, 3, 1, 9, 8], [0, 0, 2, 1, 9, 8]]          # per codeword and RBG [dB]
    cur = _report(2, sinr)
    free = np.ones(6, bool)
    assert list(_async_rbgs(unit, free, cur, SIG)) == [4, 5]
    free[4] = False                                            # taken by an earlier retx
    assert list(_async_rbgs(unit, free, cur, SIG)) == [2, 5]
    # a report of another rank says nothing about the TBs: stay on the own RBGs
    assert list(_async_rbgs(unit, free, _report(3, sinr), SIG)) == [0, 1]
    assert list(_async_rbgs(unit, free, None, SIG)) == [0, 1]
    # RBGs with another RB pattern would break chase combining: stay
    sig = SIG[:4] + [(2,), (2,)]
    assert list(_async_rbgs(unit, np.ones(6, bool), cur, sig)) == [0, 1]
    # too few free RBGs and the own ones taken: wait
    free = np.zeros(6, bool)
    free[3] = True
    assert _async_rbgs(unit, free, cur, SIG) is None
    # one codeword (NR): the report's sub-band SINRs are a vector
    one = [{"rbgs": np.array([2]), "rank": 4}]
    assert list(_async_rbgs(one, np.ones(6, bool), _report(4, [1, 7, 2, 0, 3, 4]), SIG)) == [1]


@pytest.mark.parametrize("mapping", ["alt1", "per_layer"])
def test_async_harq_moves_retransmissions_with_the_same_files(mapping):
    cfg, fb = _ftp3(ftp_rate_per_ue=12.0, cw_mapping=mapping)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(7))
    b = run_full_buffer_drop(cfg, dataclasses.replace(fb, harq_mode="async"),
                             np.random.default_rng(7))
    assert a.retx_moved_fraction == 0.0 and a.retx_rbg_fraction > 0
    assert 0 < b.retx_moved_fraction <= 1
    assert b.files_counted == a.files_counted and not _same(a, b)
    assert explicit_sync_is_default(cfg, fb, a)


def explicit_sync_is_default(cfg, fb, a):
    return _same(a, run_full_buffer_drop(cfg, dataclasses.replace(fb, harq_mode="sync"),
                                         np.random.default_rng(7)))


def test_harq_mode_checked():
    cfg, fb = _ftp3(ftp_rate_per_ue=5.0)
    with pytest.raises(ValueError, match="harq_mode"):
        run_full_buffer_drop(cfg, dataclasses.replace(fb, harq_mode="pinned"),
                             np.random.default_rng(0))
    cfg, fb = _full_buffer(mu_mimo=True, harq_mode="async")
    with pytest.raises(ValueError, match="SU-MIMO only"):
        run_full_buffer_drop(cfg, fb, np.random.default_rng(0))
