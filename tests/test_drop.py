"""Large-scale drop: association, geometry, wrap-around, determinism."""

import dataclasses

import numpy as np
import pytest

from nrsls.config.scenario import get_preset
from nrsls.engine.drop import generate_drop
from nrsls.engine.simulator import run_large_scale
from nrsls.link.link_budget import db2lin, lin2db
from nrsls.metrics.calibration import ks_distance
from nrsls.propagation.pathloss import O2I


@pytest.fixture(scope="module")
def drop():
    return generate_drop(get_preset("system"), np.random.default_rng(5))


def test_serving_cell_is_strongest(drop):
    u = np.arange(drop.ues.n)
    assert np.all(drop.coupling_gain_db[drop.serving_cell, u]
                  >= drop.coupling_gain_db.max(axis=0) - 1e-12)


def test_geometry_formula(drop):
    p = db2lin(drop.rx_power_dbm)
    u = np.arange(drop.ues.n)
    s = p[drop.serving_cell, u]
    g = lin2db(s / (p.sum(axis=0) - s + db2lin(drop.noise_dbm)))
    assert np.allclose(g, drop.geometry_db)


def test_noise_power(drop):
    bw = 273 * 12 * 30e3
    assert drop.noise_dbm == pytest.approx(-174 + 10 * np.log10(bw) + 9.0)


def test_cosited_cells_share_link_losses(drop):
    loss = drop.bs_gain_db - drop.coupling_gain_db     # PL + SF + pen - G_UT
    for s in range(drop.layout.n_sites):
        cells = np.nonzero(drop.layout.cell_site == s)[0]
        assert np.allclose(loss[cells], loss[cells[0]])


def test_o2i_links_and_penetration(drop):
    o2i = drop.ues.o2i
    assert np.all(drop.condition[:, o2i] == O2I)
    assert np.all(drop.condition[:, ~o2i] != O2I)
    # UT-specific O2I loss: identical on every link of a UT
    assert np.allclose(drop.penetration_db, drop.penetration_db[0])
    assert np.all(drop.penetration_db[:, ~o2i & ~drop.ues.in_car] == 0.0)


def test_legacy_o2i_is_link_specific():
    d = generate_drop(get_preset("uma", o2i_model="legacy",
                                 coupling_model="los"),
                      np.random.default_rng(6))
    pen = d.penetration_db[:, d.ues.o2i]
    assert np.all(pen >= 20.0) and np.all(pen <= 20.0 + 12.5)
    assert not np.allclose(pen, pen[0])


def test_wrap_around_makes_all_sites_equivalent():
    """UTs dropped in the centre site and in the outer ring see the same
    statistics with wrap-around; without it the outer ring looks better."""
    cfg = get_preset("uma", ue_per_cell=20, coupling_model="los")
    st = run_large_scale(cfg, n_drops=8, seed=11)
    inner, outer = st.geometry_db[st.drop_ring == 0], st.geometry_db[st.drop_ring == 2]
    ks_crit = 1.63 * np.sqrt(1 / len(inner) + 1 / len(outer))   # 1 % level
    assert ks_distance(inner, outer) < ks_crit

    st_nw = run_large_scale(dataclasses.replace(cfg, wrap_around=False),
                            n_drops=8, seed=11)
    inner_nw = st_nw.geometry_db[st_nw.drop_ring == 0]
    outer_nw = st_nw.geometry_db[st_nw.drop_ring == 2]
    assert np.median(outer_nw) > np.median(inner_nw) + 1.0


def test_runs_are_reproducible_and_parallel_safe():
    cfg = get_preset("umi", ue_per_cell=4)       # multipath coupling
    a = run_large_scale(cfg, n_drops=2, seed=7)
    b = run_large_scale(cfg, n_drops=2, seed=7, n_jobs=2)
    c = run_large_scale(cfg, n_drops=2, seed=8)
    # same random streams; BLAS thread counts may differ in the last bits
    assert np.array_equal(a.los, b.los) and np.array_equal(a.o2i, b.o2i)
    assert np.allclose(a.geometry_db, b.geometry_db, rtol=0, atol=1e-9)
    assert np.allclose(a.coupling_gain_db, b.coupling_gain_db, rtol=0,
                       atol=1e-9)
    assert not np.allclose(a.geometry_db, c.geometry_db)


def test_inh_drop():
    d = generate_drop(get_preset("inh-mixed"), np.random.default_rng(9))
    assert d.layout.n_cells == 12 and d.ues.n == 120
    assert not np.any(d.condition == O2I)
    assert np.all(d.penetration_db == 0.0)


def test_los_fraction_follows_probability():
    """Across many links the LOS share matches the mean LOS probability."""
    from nrsls.propagation.los import los_probability
    d = generate_drop(get_preset("umi", ue_per_cell=30, coupling_model="los"),
                      np.random.default_rng(10))
    out = ~d.ues.o2i
    p = los_probability("UMi", d.d2d_m[:, out], 1.5)
    n = p.size
    assert abs(d.los[:, out].mean() - p.mean()) < 4 * np.sqrt(p.mean() / n)


@pytest.mark.parametrize("name", ["rp-rural-700m", "rp-rural-lmlc",
                                  "rp-mmtc-1732m", "rp-urllc-4g"])
def test_rp180524_presets(name):
    cfg = get_preset(name, coupling_model="los")
    assert cfg.bandwidth_hz == 10e6 and cfg.bs_tx_power_dbm == 46.0
    assert cfg.bs_antenna.elements_per_txru == 8 and cfg.bs_antenna.dV == 0.8
    assert cfg.min_d2d_m == 10.0 and cfg.ue_noise_figure_db == 7.0
    d = generate_drop(cfg, np.random.default_rng(12))
    assert np.all(d.ues.h_m == 1.5)                      # all UEs at 1.5 m
    assert d.ues.n == 10 * 57
