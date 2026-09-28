"""MU-MIMO: zero forcing, greedy pairing and the MU path of the engine."""

import dataclasses

import numpy as np
import pytest

from nrsls.config.scenario import get_preset
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop
from nrsls.mac.mu_mimo import greedy_pairing, unit_columns, zf


def _rand(rng, *shape):
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def test_zf_nulls_the_other_layers():
    rng = np.random.default_rng(0)
    v = unit_columns(_rand(rng, 32, 6))
    w, rho = zf(v, delta=0.0)
    assert np.allclose(np.linalg.norm(w, axis=0), 1.0)
    c = np.conj(v.T) @ w                                  # (L, L)
    assert np.allclose(c - np.diag(np.diag(c)), 0, atol=1e-10)
    assert np.all((rho > 0) & (rho <= 1 + 1e-12))
    # orthogonal reports: ZF is the reports themselves, no loss
    q, _ = np.linalg.qr(_rand(rng, 32, 4))
    w, rho = zf(q)
    assert np.allclose(rho, 1.0, atol=1e-3)


def test_pairing_takes_orthogonal_and_rejects_aligned_uts():
    rng = np.random.default_rng(1)
    q, _ = np.linalg.qr(_rand(rng, 32, 8))
    v = {0: q[:, :2], 1: q[:, 2:4], 2: q[:, 4:6],
         3: unit_columns(q[:, :2] + 0.01 * _rand(rng, 32, 2))}   # ~ UT 0
    s = {u: 100.0 for u in v}
    rank = {u: 2 for u in v}
    pf = {u: 1.0 for u in v}
    group, w, est, uid = greedy_pairing(0, [1, 2, 3], v, s, rank, pf, 4, 8)
    assert sorted(group) == [0, 1, 2] and 3 not in group
    assert w.shape == (32, 6) and len(est) == 6 and list(uid) == [u for u in group
                                                                  for _ in range(2)]
    assert np.allclose(est, 100 * 2 / 6, rtol=1e-2)       # power split only
    # limits
    g, *_ = greedy_pairing(0, [1, 2, 3], v, s, rank, pf, 2, 8)
    assert len(g) == 2
    g, *_ = greedy_pairing(0, [1, 2, 3], v, s, rank, pf, 4, 4)
    assert len(g) == 2
    # a heavy MU back-off on the candidates stops the pairing
    s_mu = {u: 100.0 * 10 ** (-3.0) for u in v}
    g, *_ = greedy_pairing(0, [1, 2], v, s, rank, pf, 4, 8, s_mu)
    assert g == [0]


@pytest.fixture(scope="module")
def small():
    cfg = get_preset("rp-urllc-4g", ue_per_cell=4)
    cfg = dataclasses.replace(cfg, bs_antenna=dataclasses.replace(
        cfg.bs_antenna, N=4, Np=4))                        # 8 ports
    fb = dict(n_slots=40, warmup_slots=20, k_interferers=2, max_rank=2,
              codebook="svd")
    return cfg, fb


def test_mu_path_without_pairing_reproduces_su(small):
    cfg, fb = small
    su = run_full_buffer_drop(cfg, FullBufferConfig(**fb), np.random.default_rng(4))
    mu1 = run_full_buffer_drop(cfg, FullBufferConfig(**fb, mu_mimo=True, mu_max_ues=1),
                               np.random.default_rng(4))
    assert np.allclose(mu1.ue_se, su.ue_se, rtol=1e-6)
    assert mu1.mu_tb_fraction == 0 and mu1.mean_ues_per_rbg == 1.0


def test_mu_mimo_co_schedules_and_is_reproducible(small):
    cfg, fb = small
    a = run_full_buffer_drop(cfg, FullBufferConfig(**fb, mu_mimo=True),
                             np.random.default_rng(5))
    b = run_full_buffer_drop(cfg, FullBufferConfig(**fb, mu_mimo=True),
                             np.random.default_rng(5))
    assert np.allclose(a.ue_se, b.ue_se)
    assert a.mean_ues_per_rbg > 1.2 and a.mu_tb_fraction > 0.2
    assert a.mean_layers_per_rbg <= 8 and a.cell_se > 0
    assert 0 <= a.bler_first <= 0.5
