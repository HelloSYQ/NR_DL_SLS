"""Phase 2: LSPs, clusters/rays and the multipath port-0 RSRP."""

import numpy as np
import pytest

from nrsls.antenna.array import BSAntenna
from nrsls.config.scenario import BSAntennaConfig
from nrsls.link.rsrp import multipath_gain
from nrsls.propagation import lsp
from nrsls.propagation.clusters import N_RAYS, generate_clusters
from nrsls.propagation.pathloss import LOS, NLOS, O2I


def _lsps(family, cond, n, rng, fc=3.5, d2d=200.0, h_ut=1.5, h_bs=25.0):
    c = np.full((1, n), cond)
    xy = rng.random((n, 2)) * 1e5            # far apart: no spatial correlation
    return lsp.draw_lsps(family, fc, c, c == LOS, np.full((1, n), d2d), h_bs,
                         h_ut, np.full((1, n), 6.0), xy, np.ones(n, int), rng,
                         spatial=False)


def _flat(ls):
    return lsp.LSPs(**{k: np.broadcast_to(v, ls.ds_s.shape)[0]
                       for k, v in vars(ls).items()})


def test_lsp_statistics_uma_nlos():
    """lg DS / lg ASD moments and their cross-correlation (Table 7.5-6)."""
    rng = np.random.default_rng(0)
    ls = _lsps("uma", NLOS, 40_000, rng)
    lg_ds = np.log10(ls.ds_s[0])
    fc = 6.0                                  # UMa clips fc to 6 GHz
    assert lg_ds.mean() == pytest.approx(-0.204 * np.log10(fc) - 6.28, abs=0.01)
    assert lg_ds.std() == pytest.approx(0.39, abs=0.01)
    lg_asd = np.log10(ls.asd_deg[0])
    assert lg_asd.mean() == pytest.approx(-0.1144 * np.log10(fc) + 1.5, abs=0.01)
    assert np.corrcoef(lg_ds, lg_asd)[0, 1] == pytest.approx(0.4, abs=0.02)
    assert np.corrcoef(ls.sf_db[0], lg_asd)[0, 1] == pytest.approx(-0.6, abs=0.02)
    assert ls.sf_db[0].std() == pytest.approx(6.0, rel=0.02)
    assert ls.zsd_deg.max() <= 52.0 and ls.asd_deg.max() <= 104.0


def test_zsd_mean_and_zod_offset_spot_values():
    mu, sig, off = lsp.zsd_and_offset("uma", np.array([True, False]),
                                      np.array([300.0, 300.0]), 25.0, 1.5, 3.5)
    assert mu[0] == pytest.approx(max(-0.5, -2.1 * 0.3 + 0.75))
    assert mu[1] == pytest.approx(max(-0.5, -2.1 * 0.3 + 0.9))
    assert off[0] == 0.0
    fc = 6.0
    a, c, e = (0.208 * np.log10(fc) - 0.782, -0.13 * np.log10(fc) + 2.03,
               7.66 * np.log10(fc) - 5.96)
    assert off[1] == pytest.approx(e - 10 ** (a * np.log10(300.0) + c))
    mu, _, off = lsp.zsd_and_offset("umi", np.array([False]), np.array([100.0]),
                                    10.0, 1.5, 3.5)
    assert off[0] == pytest.approx(-10 ** (-1.5 * 2 + 3.3))


@pytest.mark.parametrize("family,cond", [("uma", NLOS), ("uma", LOS),
                                         ("uma", O2I), ("rma", LOS),
                                         ("umi", NLOS), ("inh", LOS)])
def test_cluster_properties(family, cond):
    rng = np.random.default_rng(1)
    n = 400
    ls = _flat(_lsps(family, cond, n, rng, h_bs=3.0 if family == "inh" else 25.0))
    aod = rng.uniform(-180, 180, n)
    zod = rng.uniform(91, 110, n)
    cl = generate_clusters(family, 3.5, np.full(n, cond), ls, aod, zod, rng)
    assert np.allclose(cl.power.sum(axis=1), 1.0)
    p = np.where(cl.valid, cl.power, np.nan)
    ratio = np.nanmin(p, axis=1) / np.nanmax(p, axis=1)
    assert np.all(ratio >= 10 ** -2.5 - 1e-12)             # -25 dB pruning
    assert np.all(cl.delay_s[:, 0] == 0.0)
    for d, v in zip(cl.delay_s, cl.valid):
        assert np.all(np.diff(d[v]) >= 0)                  # sorted delays
    assert np.all((cl.zod >= 0) & (cl.zod <= 180) & (cl.zoa >= 0) & (cl.zoa <= 180))
    assert cl.aod.shape[-1] == N_RAYS
    if cond == LOS:
        # the first cluster's centre is the LOS direction (ray offsets are
        # symmetric, so the circular ray mean equals the centre)
        centre = np.rad2deg(np.angle(np.exp(1j * np.deg2rad(cl.aod[:, 0, :]))
                                     .mean(axis=1)))      # circular mean
        d = (centre - aod + 180) % 360 - 180
        assert np.allclose(d, 0.0, atol=1e-9)
        assert np.all(cl.k_r > 0)
    else:
        assert np.all(cl.k_r == 0)
    if cond == O2I:
        # O2I arrival zenith is centred on the horizon
        assert abs(np.average(cl.zoa[:, :, 0], weights=cl.power) - 90) < 3


def _isotropic_port(az, zen):
    return np.ones(np.shape(az)), np.zeros(np.shape(az))    # vertical pol


def test_multipath_gain_isotropic_is_power_conserving():
    """Isotropic, vertically polarised ports: every ray has unit co-pol gain,
    so the RSRP gain is exactly 1; two orthogonal UT ports average in the
    cross-polar leakage 1/kappa."""
    rng = np.random.default_rng(2)
    n = 200
    for cond in (NLOS, LOS):
        ls = _flat(_lsps("uma", cond, n, rng))
        cl = generate_clusters("uma", 3.5, np.full(n, cond), ls,
                               rng.uniform(-180, 180, n), np.full(n, 95.0), rng)
        g1 = multipath_gain(cl, _isotropic_port, ue_pol=1)
        assert np.allclose(g1, 1.0)
        g2 = multipath_gain(cl, _isotropic_port, ue_pol=2)
        expect = (np.sum(cl.power[..., None] * 0.5 * (1 + 1 / cl.kappa), axis=(1, 2))
                  / N_RAYS / (cl.k_r + 1) + 0.5 * cl.k_r / (cl.k_r + 1))
        assert np.allclose(g2, expect)


def test_port_field_matches_port_gain():
    ant = BSAntenna(BSAntennaConfig(M=8, P=2, dV=0.8, electrical_tilt_deg=99))
    rng = np.random.default_rng(3)
    az, zen = rng.uniform(-180, 180, 500), rng.uniform(0, 180, 500)
    for tilt in (0.0, 6.0):
        ft, fp = ant.port0_field(az, zen, 150.0, downtilt_deg=tilt)
        assert np.allclose(10 * np.log10(np.abs(ft) ** 2 + np.abs(fp) ** 2),
                           ant.port_gain_db(az, zen, 150.0, downtilt_deg=tilt))
    # the azimuth-only fast path equals the general rotation
    f1 = ant.port0_field(az, zen, 150.0)
    f2 = ant.port0_field(az, zen, 150.0, downtilt_deg=1e-12)
    assert np.allclose(f1, f2, atol=1e-9)


def test_channel_matrix_power_matches_rsrp_and_is_static_without_motion():
    from nrsls.config.scenario import UEAntenna
    from nrsls.propagation.fast_fading import link_channel
    rng = np.random.default_rng(4)
    n = 6
    ls = _flat(_lsps("uma", NLOS, n, rng))
    cl = generate_clusters("uma", 3.5, np.full(n, NLOS), ls,
                           rng.uniform(-50, 50, n), np.full(n, 97.0), rng)
    bs = BSAntennaConfig(M=8, N=4, P=2, Mp=2, Np=4, dV=0.5, dH=0.5,
                         electrical_tilt_deg=100)
    ue = UEAntenna(M=1, N=2, P=2)
    g = multipath_gain(cl, lambda a, z: BSAntenna(bs).port0_field(a, z, 0.0), 2)
    lam = 3e8 / 3.5e9
    diff = []
    for link in range(n):
        H = link_channel(cl, link, bs, 0.0, ue, np.linspace(-50e6, 50e6, 64),
                         np.linspace(0, 0.5, 60), velocity_mps=(8.0, 3.0, 0.0),
                         wavelength_m=lam)
        assert H.shape == (60, 64, 4, 16)
        diff.append(10 * np.log10(np.mean(np.abs(H[..., 0]) ** 2) / g[link]))
    # averaged over time and frequency the port-0 power is the eq. 8.1-1 RSRP
    assert abs(np.mean(diff)) < 0.3 and np.max(np.abs(diff)) < 1.0
    H = link_channel(cl, 0, bs, 0.0, ue, [0.0], [0.0, 0.1, 0.3],
                     velocity_mps=(0.0, 0.0, 0.0), wavelength_m=lam)
    assert np.allclose(H[0], H[1]) and np.allclose(H[0], H[2])
