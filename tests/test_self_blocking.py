"""UT self-blocking, the user's hand grip (TR 38.901 7.6.4.1 blockage model A,
propagation.blockage): the regions of Table 7.6.4.1-1, the 30 dB loss of the
clusters arriving in them, the UT orientation that turns the array, and a
drop that is otherwise the one without the grip."""

import dataclasses

import numpy as np
import pytest

from nrsls.antenna.array import BSAntenna
from nrsls.config.scenario import BSAntennaConfig, UEAntenna, get_preset
from nrsls.engine.drop import generate_drop
from nrsls.engine.fullbuffer import run_full_buffer_drop
from nrsls.link.rsrp import multipath_gain
from nrsls.propagation.blockage import (LANDSCAPE, PORTRAIT, apply_self_blocking,
                                        blocked_power_fraction, draw_self_blocking,
                                        in_region)
from nrsls.propagation.clusters import generate_clusters
from nrsls.propagation.fast_fading import (channel_batch, concat_clusters, link_channel,
                                           subset_clusters)
from nrsls.propagation.pathloss import LOS, NLOS, O2I

from test_cw_mapping import _same
from test_fast_fading import _flat, _lsps
from test_ftp import _small as _ftp3

BS = BSAntennaConfig(M=4, N=4, P=2, Mp=1, Np=4, dV=0.5, dH=0.5, electrical_tilt_deg=100)
UE = UEAntenna(M=1, N=2, P=2)
F_HZ = np.linspace(-9e6, 9e6, 13)
LAM = 3e8 / 3.5e9
V = np.array([1.0, 0.5, 0.0])


def _clusters(cond, n, seed):
    rng = np.random.default_rng(seed)
    ls = _flat(_lsps("uma", cond, n, rng))
    cl = generate_clusters("uma", 3.5, np.full(n, cond), ls, rng.uniform(-60, 60, n),
                           np.full(n, 97.0), rng)
    return cl, rng


def _batch(cl, vel=None):
    n = cl.valid.shape[0]
    vel = np.tile(V, (n, 1)) if vel is None else vel
    return channel_batch(subset_clusters(cl, np.arange(n)), np.zeros(n), BS, UE, F_HZ,
                         0.01, vel, LAM, np.full(n, 100.0))


def _rel(a, b):
    return np.linalg.norm(a - b) / np.linalg.norm(b)


def test_regions_of_table_7_6_4_1_1():
    # portrait (one hand): AOA' in [200, 320], ZOA' in [60, 140]
    def p(a, z, rot=0.0):
        return bool(in_region(PORTRAIT, rot, a, z))
    assert p(260, 100) and p(201, 61) and p(319, 139) and p(-100, 100)
    assert not (p(199, 100) or p(321, 100) or p(260, 59) or p(260, 141))
    # the region turns with the UT: phi' = phi - alpha
    assert p(-10, 100, rot=90.0) and not p(260, 100, rot=90.0)

    # landscape (two hands): AOA' in [-40, 120], ZOA' in [72.5, 147.5]
    def l(a, z, rot=0.0):
        return bool(in_region(LANDSCAPE, rot, a, z))
    assert l(40, 110) and l(-39, 73) and l(119, 147) and l(330, 100)
    assert not (l(-41, 110) or l(121, 110) or l(40, 72) or l(40, 148))
    # per-link modes and orientations broadcast over (L, N) angles
    hit = in_region(np.array([PORTRAIT, LANDSCAPE]), np.array([0.0, 180.0]),
                    np.array([[260.0, 40.0], [100.0, 220.0]]), np.full((2, 2), 100.0))
    assert hit.tolist() == [[True, False], [False, True]]


def test_grips_are_drawn_with_the_landscape_share_and_uniform_orientations():
    sb = draw_self_blocking(20_000, 0.25, 30.0, np.random.default_rng(0))
    assert np.mean(sb.mode == LANDSCAPE) == pytest.approx(0.25, abs=0.01)
    assert sb.bearing_deg.min() >= 0 and sb.bearing_deg.max() < 360
    assert np.histogram(sb.bearing_deg, bins=4, range=(0, 360))[0].min() > 4800
    assert sb.loss_db == 30.0


@pytest.mark.parametrize("cond", [NLOS, LOS, O2I])
def test_a_cluster_loses_30_db_when_its_centre_arrives_in_the_region(cond):
    n = 300
    cl, rng = _clusters(cond, n, 3)
    # the stored centres are the circular means of the (symmetric) rays
    centre = np.rad2deg(np.angle(np.exp(1j * np.deg2rad(cl.aoa)).mean(axis=-1)))
    assert np.allclose(((centre - cl.aoa_c + 180) % 360 - 180)[cl.valid], 0, atol=1e-6)
    assert np.all((cl.zoa_c >= 0) & (cl.zoa_c <= 180))
    sb = draw_self_blocking(n, 0.5, 30.0, rng)
    b = apply_self_blocking(cl, sb)
    hit = in_region(sb.mode, sb.bearing_deg, cl.aoa_c, cl.zoa_c)
    assert np.array_equal(b.gain == 1e-3, hit) and np.all((b.gain == 1.0) | hit)
    assert np.array_equal(b.ue_bearing_deg, sb.bearing_deg)
    # about the region's share of the azimuths (1/3 portrait, 4/9 landscape)
    # times the arrivals within its zenith band
    share = (hit & cl.valid).sum() / cl.valid.sum()
    assert 0.15 < share < 0.45
    lost = blocked_power_fraction(b)
    assert np.all((lost >= 0) & (lost <= 1 - 1e-3 + 1e-12)) and lost.mean() > 0.1
    assert np.all(blocked_power_fraction(cl) == 0)
    if cond == LOS:
        # the LOS ray is a ray of the first cluster and points the same way
        assert np.array_equal(b.los_gain < 1, in_region(sb.mode, sb.bearing_deg,
                                                        cl.los_aoa, cl.los_zoa))
        assert np.array_equal(b.los_gain, b.gain[:, 0])
    # the fields travel with subsets and concatenations
    s = subset_clusters(b, [4, 1])
    assert np.array_equal(s.gain, b.gain[[4, 1]].astype(np.float32))
    assert np.array_equal(concat_clusters([s, s]).ue_bearing_deg, np.tile(b.ue_bearing_deg[[4, 1]], 2))
    with pytest.raises(ValueError, match="gain"):
        concat_clusters([s, subset_clusters(cl, [0])])


@pytest.mark.parametrize("cond", [NLOS, LOS])
def test_blocking_scales_channel_and_rsrp(cond):
    cl, _ = _clusters(cond, 4, 5)
    n = 4
    h0 = _batch(cl)
    att = 1e-3
    every = dataclasses.replace(cl, gain=np.full(cl.power.shape, att), los_gain=np.full(n, att))
    assert _rel(_batch(every), np.sqrt(att) * h0) < 1e-5
    ones = dataclasses.replace(cl, gain=np.ones(cl.power.shape), los_gain=np.ones(n))
    assert _rel(_batch(ones), h0) < 1e-6
    port0 = lambda a, z: BSAntenna(BS).port0_field(a, z, 0.0)
    assert np.allclose(multipath_gain(every, port0, 2), att * multipath_gain(cl, port0, 2))
    # one blocked cluster takes its share out of the RSRP
    one = dataclasses.replace(cl, gain=np.where(np.arange(cl.power.shape[1]) == 1, att, 1.0),
                              los_gain=np.ones(n))
    assert np.all(multipath_gain(one, port0, 2) < multipath_gain(cl, port0, 2))
    # per-link synthesis agrees with the batch
    for l in range(n):
        hl = link_channel(every, l, BS, 0.0, UE, F_HZ, [0.01], velocity_mps=V,
                          wavelength_m=LAM, d3d_m=100.0)[0]
        assert _rel(hl, _batch(every)[l]) < 1e-4


def test_turning_the_ut_turns_its_array_not_the_world():
    cl, _ = _clusters(LOS, 4, 6)
    rot = np.array([0.0, 90.0, 200.0, 315.0])
    turned = dataclasses.replace(cl, ue_bearing_deg=rot)
    h = _batch(turned)
    assert _rel(h[0], _batch(cl)[0]) < 1e-6 and _rel(h[1], _batch(cl)[1]) > 0.1
    # the same as an unturned UT with every arrival azimuth and the velocity
    # seen in its LCS (the Doppler shifts are GCS quantities and unchanged)
    a = np.deg2rad(-rot)
    v_lcs = np.stack([np.cos(a) * V[0] - np.sin(a) * V[1],
                      np.sin(a) * V[0] + np.cos(a) * V[1], np.zeros(4)], -1)
    lcs = dataclasses.replace(cl, aoa=cl.aoa - rot[:, None, None], los_aoa=cl.los_aoa - rot)
    assert _rel(h, _batch(lcs, v_lcs)) < 1e-4
    for l in range(4):
        hl = link_channel(turned, l, BS, 0.0, UE, F_HZ, [0.01], velocity_mps=V,
                          wavelength_m=LAM, d3d_m=100.0)[0]
        assert _rel(hl, h[l]) < 1e-4


def _cfg(**kw):
    return get_preset("du-a", ue_per_cell=2, **kw)


def test_drop_with_the_grip_is_the_drop_without_it_minus_the_blocked_power():
    cfg = _cfg()
    a = generate_drop(cfg, np.random.default_rng(2), keep_clusters=True)
    b = generate_drop(dataclasses.replace(cfg, ue_self_blocking=True),
                      np.random.default_rng(2), keep_clusters=True)
    assert a.self_blocking is None and b.self_blocking is not None
    for f in ("pathloss_db", "shadow_fading_db", "penetration_db", "condition", "d3d_m"):
        assert np.array_equal(getattr(a, f), getattr(b, f)), f
    assert np.array_equal(a.ues.xy, b.ues.xy)
    for ca, cb in zip(a.clusters, b.clusters):
        for f in ("power", "aoa", "zod", "phase", "kappa", "aoa_c"):
            assert np.array_equal(getattr(ca, f), getattr(cb, f)), f
        assert ca.gain is None and cb.gain is not None
    d = b.coupling_gain_db - a.coupling_gain_db
    assert d.max() <= 1e-9 and d.min() >= -30.0 - 1e-9 and d.mean() < -1.0
    # a UT attaches to its strongest cell after the grip
    assert np.array_equal(b.serving_cell, np.argmax(b.coupling_gain_db, axis=0))
    assert np.all(b.self_blocking.bearing_deg == b.clusters[0].ue_bearing_deg)
    with pytest.raises(ValueError, match="multipath"):
        _cfg(ue_self_blocking=True, coupling_model="los")
    with pytest.raises(ValueError, match="landscape"):
        _cfg(self_blocking_landscape_ratio=1.5)
    # no loss: only the orientation (array) changes, attachment does not
    c0 = generate_drop(dataclasses.replace(cfg, ue_self_blocking=True, self_blocking_db=0.0),
                       np.random.default_rng(2), keep_clusters=True)
    assert np.allclose(c0.coupling_gain_db, a.coupling_gain_db)


def test_ftp_run_with_the_grip_keeps_the_files():
    cfg, fb = _ftp3(ftp_rate_per_ue=12.0)
    a = run_full_buffer_drop(cfg, fb, np.random.default_rng(7))
    grip = dataclasses.replace(cfg, ue_self_blocking=True)
    b = run_full_buffer_drop(grip, fb, np.random.default_rng(7))
    assert b.files_counted == a.files_counted and not _same(a, b)
    off = dataclasses.replace(cfg, ue_self_blocking=False, self_blocking_db=12.0)
    assert _same(a, run_full_buffer_drop(off, fb, np.random.default_rng(7)))


# --- per-antenna hand loss (hand_loss_db; not in TR 38.901) -------------------
def test_hand_covers_one_antenna_in_portrait_and_two_in_landscape():
    a = draw_self_blocking(4000, 0.5, 30.0, np.random.default_rng(4))
    b = draw_self_blocking(4000, 0.5, 30.0, np.random.default_rng(4), n_ports=4,
                           hand_loss_db=6.0)
    # mode and orientation are those without the hand loss
    assert a.port_gain is None and b.port_gain.shape == (4000, 4)
    assert np.array_equal(a.mode, b.mode) and np.array_equal(a.bearing_deg, b.bearing_deg)
    att = 10 ** -0.6
    assert set(np.unique(b.port_gain)) == {att, 1.0}
    n_cov = np.sum(b.port_gain < 1, axis=1)
    assert np.all(n_cov[b.mode == PORTRAIT] == 1) and np.all(n_cov[b.mode == LANDSCAPE] == 2)
    # every antenna is covered equally often: 1/4 (portrait), 2/4 (landscape)
    assert np.allclose(np.mean(b.port_gain[b.mode == PORTRAIT] < 1, axis=0), 0.25, atol=0.04)
    assert np.allclose(np.mean(b.port_gain[b.mode == LANDSCAPE] < 1, axis=0), 0.5, atol=0.04)
    # other counts; never more than the UT has antennas
    c = draw_self_blocking(500, 0.5, 30.0, np.random.default_rng(4), n_ports=2,
                           hand_loss_db=3.0, covered=(0, 3))
    n_cov = np.sum(c.port_gain < 1, axis=1)
    assert np.all(n_cov[c.mode == PORTRAIT] == 0) and np.all(n_cov[c.mode == LANDSCAPE] == 2)
    with pytest.raises(ValueError):
        draw_self_blocking(5, 0.5, 30.0, np.random.default_rng(4), hand_loss_db=6.0)


@pytest.mark.parametrize("cond", [LOS, NLOS])
def test_hand_loss_scales_the_rows_of_the_channel(cond):
    cl, rng = _clusters(cond, 6, 11)
    sb0 = draw_self_blocking(6, 0.5, 30.0, np.random.default_rng(5))
    sb = draw_self_blocking(6, 0.5, 30.0, np.random.default_rng(5), n_ports=4, hand_loss_db=6.0)
    grip, hand = apply_self_blocking(cl, sb0), apply_self_blocking(cl, sb)
    assert grip.port_gain is None and np.array_equal(hand.port_gain, sb.port_gain)
    h0, h = _batch(grip), _batch(hand)
    amp = np.sqrt(sb.port_gain)[:, None, :, None]                    # (L, 1, U, 1)
    assert np.allclose(h, h0 * amp, rtol=1e-5, atol=1e-9)
    # a covered antenna is 6 dB down, the others untouched
    p0, p = np.sum(np.abs(h0) ** 2, axis=(1, 3)), np.sum(np.abs(h) ** 2, axis=(1, 3))
    assert np.allclose(10 * np.log10(p / p0), 10 * np.log10(sb.port_gain), atol=1e-3)
    # the single-link synthesis and a subset of the links agree
    for l in range(6):
        hl = link_channel(hand, l, BS, 0.0, UE, F_HZ, [0.01], velocity_mps=V,
                          wavelength_m=LAM, d3d_m=100.0)[0]
        assert _rel(hl, h[l]) < 1e-4
    sub = subset_clusters(hand, np.array([4, 1]))
    assert np.array_equal(sub.port_gain, sb.port_gain[[4, 1]])
    assert concat_clusters([sub, sub]).port_gain.shape == (4, 4)
    # port-0 RSRP (cell selection, coupling gain) is that of an uncovered antenna
    port0 = lambda a, z: BSAntenna(BS).port0_field(a, z, 0.0)
    assert np.array_equal(multipath_gain(hand, port0, 2), multipath_gain(grip, port0, 2))


def test_hand_loss_in_a_drop_and_in_the_system():
    cfg = _cfg(ue_self_blocking=True)
    a = generate_drop(cfg, np.random.default_rng(2), keep_clusters=True)
    b = generate_drop(dataclasses.replace(cfg, hand_loss_db=6.0), np.random.default_rng(2),
                      keep_clusters=True)
    # the drop of the grip, with the covered antennas on top
    assert a.self_blocking.port_gain is None and b.self_blocking.port_gain.shape == (b.ues.n, 4)
    assert np.array_equal(a.coupling_gain_db, b.coupling_gain_db)
    assert np.array_equal(a.serving_cell, b.serving_cell)
    assert np.array_equal(a.self_blocking.mode, b.self_blocking.mode)
    for ca, cb in zip(a.clusters, b.clusters):
        assert np.array_equal(ca.gain, cb.gain) and ca.port_gain is None
        assert np.array_equal(cb.port_gain, b.self_blocking.port_gain)
    with pytest.raises(ValueError, match="ue_self_blocking"):
        _cfg(hand_loss_db=6.0)
    with pytest.raises(ValueError, match="hand_loss_db"):
        _cfg(ue_self_blocking=True, hand_loss_db=-1.0)
    with pytest.raises(ValueError, match="hand_covered_antennas"):
        _cfg(ue_self_blocking=True, hand_covered_antennas=(1,))
    # system run: the same files; no hand loss is the grip run exactly
    cfg, fb = _ftp3(ftp_rate_per_ue=12.0)
    grip = dataclasses.replace(cfg, ue_self_blocking=True)
    g = run_full_buffer_drop(grip, fb, np.random.default_rng(7))
    h = run_full_buffer_drop(dataclasses.replace(grip, hand_loss_db=10.0), fb,
                             np.random.default_rng(7))
    assert h.files_counted == g.files_counted and not _same(g, h)
    z = run_full_buffer_drop(dataclasses.replace(grip, hand_loss_db=0.0,
                                                 hand_covered_antennas=(3, 4)), fb,
                             np.random.default_rng(7))
    assert _same(g, z)
    # two of the four antennas 15 dB down: fewer layers
    h2 = run_full_buffer_drop(dataclasses.replace(grip, hand_loss_db=15.0,
                                                  hand_covered_antennas=(2, 2)), fb,
                              np.random.default_rng(7))
    assert h2.mean_rank < g.mean_rank
