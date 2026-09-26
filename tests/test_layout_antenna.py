"""Layout, wrap-around, UT dropping and the gNB antenna."""

import numpy as np
import pytest

from nrsls.antenna.array import BSAntenna
from nrsls.config.scenario import BSAntennaConfig, get_preset
from nrsls.topology.layout import (build_layout, hex_site_positions,
                                   hex_wrap_offsets)
from nrsls.topology.ue_drop import drop_ues


def _hex_dist(xy, isd):
    q = (xy[..., 0] - xy[..., 1] / np.sqrt(3.0)) / isd
    r = xy[..., 1] * 2.0 / np.sqrt(3.0) / isd
    return np.rint(np.max(np.abs([q, r, q + r]), axis=0)).astype(int)


def test_hex_sites():
    sites = hex_site_positions(500.0, 2)
    assert sites.shape == (19, 2)
    assert np.allclose(sites[0], 0.0)
    d = np.hypot(*(sites[:, None] - sites[None]).transpose(2, 0, 1))
    np.fill_diagonal(d, np.inf)
    assert np.allclose(d.min(axis=1), 500.0)
    assert list(np.bincount(_hex_dist(sites, 500.0))) == [1, 6, 12]


def test_wrap_around_tiles_the_plane():
    isd = 1.0
    sites = hex_site_positions(isd, 2)
    offs = hex_wrap_offsets(isd, 2)
    assert np.allclose(np.hypot(*offs[1:].T), np.sqrt(19.0))
    allpts = (sites[None] + offs[:, None]).reshape(-1, 2)
    keys = {tuple(np.round(p, 6)) for p in allpts}
    assert len(keys) == 7 * 19                        # no overlap
    # every lattice point within hex distance 4 of the centre is covered
    for q in range(-4, 5):
        for r in range(-4, 5):
            if max(abs(q), abs(r), abs(q + r)) <= 4:
                p = isd * np.array([q + r / 2.0, r * np.sqrt(3.0) / 2.0])
                assert tuple(np.round(p, 6)) in keys


def test_virtual_positions_match_infinite_tiling():
    """For UTs inside the cluster the 7 copies give the same closest site
    distances as a much larger patch of the periodic tiling."""
    cfg = get_preset("uma", ue_per_cell=5)
    layout = build_layout(cfg)
    ues = drop_ues(cfg, layout, np.random.default_rng(0))
    d7 = np.hypot(*(ues.xy[None] - layout.virtual_site_xy(ues.xy))
                  .transpose(2, 0, 1))
    t1, t2 = layout.wrap_offsets[1], layout.wrap_offsets[2]
    shifts = np.array([a * t1 + b * t2 for a in range(-3, 4)
                       for b in range(-3, 4)])
    cand = layout.site_xy[:, None, :] + shifts[None]             # (S, K, 2)
    dk = np.hypot(*(ues.xy[None, None] - cand[:, :, None])
                  .transpose(3, 0, 1, 2))                         # (S, K, U)
    assert np.allclose(d7, dk.min(axis=1))
    # the closest site copy is never farther than the site-hexagon radius
    assert np.all(d7.min(axis=0) <= cfg.isd_m / np.sqrt(3.0) + 1e-6)


def test_sector_rhombi_tile_site_hexagon():
    cfg = get_preset("uma")
    layout = build_layout(cfg)
    rng = np.random.default_rng(1)
    for cell in range(3):
        o, a, b = layout.sector_rhombus(cell)
        assert abs(a[0] * b[1] - a[1] * b[0]) == pytest.approx(
            3 * np.sqrt(3) / 2 * (cfg.isd_m / np.sqrt(3)) ** 2 / 3)
        st = rng.random((500, 2))
        pts = o + st[:, :1] * a + st[:, 1:] * b
        d = np.hypot(*(pts[None] - layout.virtual_site_xy(pts))
                     .transpose(2, 0, 1))
        assert np.all(np.argmin(d, axis=0) == 0)      # inside site 0's hexagon
        ang = np.rad2deg(np.arctan2(pts[:, 1], pts[:, 0]))
        off = (ang - layout.cell_bearing_deg[cell] + 180) % 360 - 180
        assert np.all(np.abs(off) <= 60 + 1e-9)       # within +-60 deg


def test_ue_drop_properties():
    cfg = get_preset("uma", ue_per_cell=40)
    layout = build_layout(cfg)
    ues = drop_ues(cfg, layout, np.random.default_rng(2))
    assert ues.n == 40 * 57
    assert np.all(np.bincount(ues.drop_cell) == 40)
    d = np.hypot(*(ues.xy - layout.site_xy[layout.cell_site[ues.drop_cell]]).T)
    assert d.min() >= cfg.min_d2d_m
    assert ues.o2i.mean() == pytest.approx(0.8, abs=0.03)
    ind = ues.o2i
    assert np.all(ues.h_m[~ind] == 1.5)
    assert np.allclose(ues.h_m[ind], 3.0 * (ues.floor[ind] - 1) + 1.5)
    assert ues.floor.min() == 1 and ues.floor.max() <= 8
    # min of two U(0, 25): mean 25 / 3
    assert ues.d2d_in_m[ind].mean() == pytest.approx(25 / 3, abs=0.5)
    assert np.all(ues.d2d_in_m[~ind] == 0)
    assert ues.high_loss[ind].mean() == pytest.approx(0.2, abs=0.03)
    assert not ues.high_loss[~ind].any()


def test_inh_layout_and_drop():
    cfg = get_preset("inh-open")
    layout = build_layout(cfg)
    assert layout.n_sites == 12 and layout.n_cells == 12
    assert np.allclose(sorted(set(layout.site_xy[:, 0])),
                       [-50, -30, -10, 10, 30, 50])
    assert np.allclose(sorted(set(layout.site_xy[:, 1])), [-10, 10])
    ues = drop_ues(cfg, layout, np.random.default_rng(3))
    assert ues.n == 120
    assert np.all(np.abs(ues.xy[:, 0]) <= 60) and np.all(np.abs(ues.xy[:, 1]) <= 25)
    assert not ues.o2i.any() and np.all(ues.h_m == 1.0)


def test_antenna_peak_and_element_cuts():
    ant = BSAntenna(BSAntennaConfig(M=10, dV=0.8, electrical_tilt_deg=102.0))
    assert ant.peak_gain_dbi == pytest.approx(18.0)
    g0 = ant.port_gain_db(30.0, 102.0, 30.0)
    # on the tilt: element vertical cut -12 (12/65)^2 dB + array gain 10 dB
    assert float(g0) == pytest.approx(18.0 - 12 * (12 / 65) ** 2, abs=1e-6)
    # horizontal 3 dB beamwidth 65 deg
    g3 = ant.port_gain_db(30.0 + 32.5, 102.0, 30.0)
    assert float(g0 - g3) == pytest.approx(3.0, abs=1e-6)
    # behind the panel the element is capped at A_max = 30 dB
    gb = ant.port_gain_db(210.0, 102.0, 30.0)
    assert float(g0 - gb) == pytest.approx(30.0 - 12 * (12 / 65) ** 2, abs=1e-6)
    # first null of the 10-element, 0.8-lambda sub-array
    th_null = np.rad2deg(np.arccos(np.cos(np.deg2rad(102.0)) + 1 / 8))
    assert float(g0 - ant.port_gain_db(30.0, th_null, 30.0)) > 30.0


def test_antenna_mechanical_tilt_points_down():
    cfg = BSAntennaConfig(M=4, dV=0.5, electrical_tilt_deg=90.0,
                          mechanical_downtilt_deg=90.0)
    ant = BSAntenna(cfg)
    zen = np.linspace(95, 180, 200)
    g = ant.port_gain_db(np.zeros_like(zen), zen, 0.0)
    assert zen[np.argmax(g)] == pytest.approx(180.0, abs=0.5)
    assert float(g.max()) == pytest.approx(8.0 + 10 * np.log10(4), abs=0.05)
