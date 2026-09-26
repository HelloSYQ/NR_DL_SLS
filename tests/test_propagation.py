"""Pathloss, LOS probability, O2I loss and shadow fading vs TR 38.901.

The spot values were computed independently from the Table 7.4.1-1,
7.4.2-1 and 7.4.3-1/2 formulas (not with this package).
"""

import numpy as np
import pytest

from nrsls.propagation import lsp, o2i, pathloss
from nrsls.propagation.los import los_probability
from nrsls.propagation.pathloss import LOS, NLOS, O2I


def d3(d2, hb, hu):
    return np.hypot(d2, hb - hu)


@pytest.mark.parametrize("fn,d2,hb,hu,fc_ghz,expected", [
    ("uma_los", 100, 25, 1.5, 3.5, 83.1382),      # below the breakpoint
    ("uma_los", 800, 25, 1.5, 3.5, 105.5382),     # beyond d'_BP = 560 m
    ("uma_nlos", 100, 25, 1.5, 3.5, 103.0375),
    ("uma_nlos", 300, 25, 16.5, 6.0, 116.9157),   # upper floor (h_UT term)
    ("umi_los", 50, 10, 1.5, 3.5, 79.0896),
    ("umi_los", 500, 10, 1.5, 3.5, 107.1138),     # beyond d'_BP = 210 m
    ("umi_nlos", 120, 10, 1.5, 6.0, 112.4081),
    ("rma_los", 300, 35, 1.5, 0.7, 79.8462),      # PL1
    ("rma_los", 1000, 35, 1.5, 0.7, 93.3816),     # PL2, d_BP = 770 m
    ("rma_los", 5000, 35, 1.5, 3.5, 125.9690),
    ("rma_nlos", 2000, 35, 1.5, 0.7, 128.0677),
])
def test_pathloss_spot_values(fn, d2, hb, hu, fc_ghz, expected):
    pl = getattr(pathloss, fn)(d2, d3(d2, hb, hu), hb, hu, fc_ghz * 1e9)
    assert float(pl) == pytest.approx(expected, abs=1e-3)


def test_inh_spot_values():
    for d2, los, nlos in [(10, 60.7287, 69.4735), (60, 74.0475, 98.9597)]:
        dd = d3(d2, 3.0, 1.0)
        assert float(pathloss.inh_los(dd, 3.5e9)) == pytest.approx(los, abs=1e-3)
        assert float(pathloss.inh_nlos(dd, 3.5e9)) == pytest.approx(nlos, abs=1e-3)


@pytest.mark.parametrize("family,hb,hu,fc,tol", [
    ("uma", 25.0, 1.5, 3.5e9, 1e-4), ("uma", 25.0, 7.5, 6e9, 1e-4),
    ("umi", 10.0, 1.5, 3.5e9, 1e-4),
    # RMa switches on d2D but evaluates PL1(d_BP) + 40 log10(d3D / d_BP), so
    # the spec formula itself has a small (millidecibel) step at d_BP
    ("rma", 35.0, 1.5, 0.7e9, 0.02)])
def test_los_pathloss_continuous_at_breakpoint(family, hb, hu, fc, tol):
    if family == "rma":
        d_bp = pathloss.rma_breakpoint(hb, hu, fc)
    else:
        d_bp = 4 * (hb - 1.0) * (hu - 1.0) * fc / 3e8
    fn = getattr(pathloss, f"{family}_los")
    lo = fn(d_bp * (1 - 1e-9), d3(d_bp * (1 - 1e-9), hb, hu), hb, hu, fc)
    hi = fn(d_bp * (1 + 1e-9), d3(d_bp * (1 + 1e-9), hb, hu), hb, hu, fc)
    assert float(lo) == pytest.approx(float(hi), abs=tol)


@pytest.mark.parametrize("family,hb", [("uma", 25.0), ("umi", 10.0),
                                       ("rma", 35.0), ("inh", 3.0)])
def test_nlos_never_below_los(family, hb):
    d2 = np.linspace(10, 2000 if family != "inh" else 100, 400)
    hu = 1.0 if family == "inh" else 1.5
    args = (d2, d3(d2, hb, hu), hb, hu, 3.5e9)
    los = pathloss.basic_pathloss_db(family, True, *args)
    nlos = pathloss.basic_pathloss_db(family, False, *args)
    assert np.all(nlos >= los - 1e-9)


def test_uma_effective_height_distribution():
    rng = np.random.default_rng(0)
    n = 200_000
    # below 13 m h_E is always 1 m
    assert np.all(pathloss.sample_uma_h_e(np.full(1000, 150.0),
                                          np.full(1000, 10.5), rng) == 1.0)
    # h_UT = 22.5 m, d2D = 150 m: P(h_E = 1) = 1 / (1 + C) = 0.4103,
    # otherwise uniform on {12, 15, 18, 21}
    h = pathloss.sample_uma_h_e(np.full(n, 150.0), np.full(n, 22.5), rng)
    assert np.mean(h == 1.0) == pytest.approx(0.41033, abs=0.005)
    others = h[h != 1.0]
    vals, counts = np.unique(others, return_counts=True)
    assert list(vals) == [12.0, 15.0, 18.0, 21.0]
    assert np.allclose(counts / counts.sum(), 0.25, atol=0.01)


@pytest.mark.parametrize("scenario,d,h,expected", [
    ("UMi", 100.0, 1.5, 0.230985), ("UMa", 100.0, 1.5, 0.347671),
    ("UMa", 100.0, 22.5, 0.554273), ("InH-open", 20.0, 1.0, 0.809074),
    ("InH-open", 60.0, 1.0, 0.512658), ("InH-mixed", 3.0, 1.0, 0.681827),
    ("InH-mixed", 10.0, 1.0, 0.287424), ("RMa", 510.0, 1.5, 0.606531),
    ("UMa", 17.0, 22.5, 1.0), ("UMi", 18.0, 1.5, 1.0), ("RMa", 9.0, 1.5, 1.0),
])
def test_los_probability(scenario, d, h, expected):
    assert float(los_probability(scenario, d, h)) == pytest.approx(expected,
                                                                   abs=1e-5)


@pytest.mark.parametrize("fc,low,high", [(3.5, 12.6975, 26.8498),
                                         (6.0, 13.4022, 30.6935),
                                         (28.0, 17.8288, 37.9490)])
def test_wall_loss(fc, low, high):
    assert float(o2i.wall_loss_db(fc, False)) == pytest.approx(low, abs=1e-3)
    assert float(o2i.wall_loss_db(fc, True)) == pytest.approx(high, abs=1e-3)


def test_o2i_loss_statistics():
    rng = np.random.default_rng(1)
    n = 100_000
    d_in = np.full(n, 10.0)
    for high, sigma in [(False, 4.4), (True, 6.5)]:
        loss = o2i.o2i_loss_db(6.0, np.ones(n, bool), np.full(n, high), d_in,
                               rng)
        assert loss.mean() == pytest.approx(
            float(o2i.wall_loss_db(6.0, high)) + 5.0, abs=0.1)
        assert loss.std() == pytest.approx(sigma, abs=0.1)
    out = o2i.o2i_loss_db(6.0, np.zeros(10, bool), np.zeros(10, bool),
                          np.zeros(10), rng)
    assert np.all(out == 0.0)
    assert np.allclose(o2i.legacy_o2i_loss_db([True, False], [10.0, 7.0]),
                       [25.0, 0.0])


def test_shadow_fading_std_table():
    cond = np.array([LOS, NLOS, O2I])
    assert np.allclose(pathloss.shadow_fading_std_db("uma", cond), [4, 6, 7])
    assert np.allclose(pathloss.shadow_fading_std_db("umi", cond), [4, 7.82, 7])
    assert np.allclose(pathloss.shadow_fading_std_db("inh", cond[:2]),
                       [3, 8.03])
    # RMa LOS: 4 dB below, 6 dB beyond the breakpoint (770 m at 0.7 GHz)
    s = pathloss.shadow_fading_std_db("rma", np.array([LOS, LOS, NLOS, O2I]),
                                      np.array([500.0, 1000.0, 500.0, 500.0]),
                                      35.0, 1.5, 0.7e9)
    assert np.allclose(s, [4, 6, 8, 8])


def test_correlated_field_statistics():
    rng = np.random.default_rng(2)
    xy = np.array([[0.0, 0.0], [20.0, 0.0], [0.0, 50.0], [0.0, 0.0]])
    floor = np.array([1, 1, 1, 2])            # last UT: same spot, other floor
    f = lsp.correlated_fields(40_000, xy, floor, 37.0, rng)
    c = np.corrcoef(f.T)
    assert np.allclose(np.diag(np.cov(f.T)), 1.0, atol=0.03)
    assert c[0, 1] == pytest.approx(np.exp(-20 / 37), abs=0.02)
    assert c[0, 2] == pytest.approx(np.exp(-50 / 37), abs=0.02)
    assert abs(c[0, 3]) < 0.02                # different floors: independent


def test_shadow_fading_uses_condition_fields():
    rng = np.random.default_rng(3)
    n_sites, n_ue = 3, 400
    xy = rng.random((n_ue, 2)) * 500
    cond = rng.integers(0, 3, (n_sites, n_ue))
    sigma = pathloss.shadow_fading_std_db("uma", cond)
    sf = np.concatenate([lsp.shadow_fading_db("uma", cond, sigma, xy,
                                              np.ones(n_ue, int), rng)
                         for _ in range(30)], axis=1)
    cc = np.tile(cond, 30)
    for c, s in [(LOS, 4.0), (NLOS, 6.0), (O2I, 7.0)]:
        assert sf[cc == c].std() == pytest.approx(s, rel=0.06)


def test_rma_lmlc_nlos_offset():
    """ITU-R M.2412 LMLC: PL_NLOS = max(PL_LOS, PL'_NLOS - 12)."""
    d2, hb, hu, fc = 3000.0, 35.0, 1.5, 0.7e9
    dd = d3(d2, hb, hu)
    los = float(pathloss.rma_los(d2, dd, hb, hu, fc))
    std = float(pathloss.rma_nlos(d2, dd, hb, hu, fc))
    lmlc = float(pathloss.rma_nlos(d2, dd, hb, hu, fc, nlos_offset_db=12.0))
    assert lmlc == pytest.approx(max(los, std - 12.0))
    assert std - lmlc == pytest.approx(12.0)      # NLOS term dominates here
