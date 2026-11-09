"""Calibration benchmark (nrsls.validation.calibration_bench) and the
analog-beam calibration mode it needs for Dense Urban config A."""

import dataclasses
import json
import os

import numpy as np
import pytest

from nrsls.antenna.array import BSAntenna, af_power
from nrsls.config.scenario import BSAntennaConfig, get_preset
from nrsls.engine.drop import generate_drop
from nrsls.validation import calibration_bench as cb

REFS = os.path.join(os.path.dirname(__file__), "..", "refs", "rp180524")


def _companies(n=12, spread=1.0):
    """Synthetic company curves: a common CDF shape plus a per-company
    offset, on the 0..100 percentile grid of the RP-180524 sheets."""
    pct = np.arange(101.0)
    base = np.linspace(-10, 20, 101)
    offsets = np.linspace(-spread, spread, n)          # evenly spread companies
    return pct, base[None, :] + offsets[:, None], base


def test_af_power_peak_and_nulls():
    assert af_power(0.0, 8) == pytest.approx(8.0)
    assert af_power(2 * np.pi / 8, 8) == pytest.approx(0.0, abs=1e-12)   # first null
    psi = np.linspace(-np.pi, np.pi, 1001)
    # unit-norm weights: the array factor averages to 1 over a period
    assert np.mean(af_power(psi, 8)) == pytest.approx(1.0, rel=1e-2)


def test_beam_power_points_where_steered():
    ant = BSAntenna(BSAntennaConfig(M=8, N=8, P=2, Mp=2, Np=1, dV=0.8, dH=0.5,
                                    mechanical_downtilt_deg=0.0))
    beams = [(112.5, 33.75), (157.5, -11.25)]
    # GCS directions of the two beams for a cell with bearing 150 deg
    p = ant.beam_power(np.array([150 + 33.75, 150 - 11.25]), np.array([112.5, 157.5]),
                       150.0, beams)
    assert p.shape == (2, 2)
    assert np.diag(p) == pytest.approx([32.0, 32.0])      # K L = 4 x 8
    assert p[0, 1] < 1.0 and p[1, 0] < 1.0


def test_load_companies_matches_index():
    index = {(d["sheet"], d["metric"]): d for d in
             json.load(open(os.path.join(REFS, "index.json")))}
    for case in cb.CASES:
        for metric in cb.METRICS:
            pct, names, vals = cb.load_companies(case.sheet, metric)
            ref = index[(case.sheet, metric)]
            assert len(names) == vals.shape[0] == ref["n_companies"]
            assert vals.shape[1] == pct.size == 101
            # the sheet's p50 in the index is the mean over the companies
            assert np.nanmean(vals[:, 50]) == pytest.approx(ref["p50"], abs=0.05)


def test_peer_test_consensus_passes_outlier_fails():
    pct, comp, base = _companies()
    consensus = np.interp(np.random.default_rng(1).random(20000) * 100, pct,
                          comp.mean(axis=0))
    st = cb.peer_stats(consensus, pct, comp)
    # sampling noise of the simulated percentiles (~0.05 dB) can put it just
    # behind the most central company
    assert st["deviation_db"] < 0.1 and st["rank"] <= 2
    assert st["envelope_share"] == 1.0 and cb.verdict(st) == "PASS"

    far = consensus + 5.0                       # 5 dB off, companies spread 1 dB
    st = cb.peer_stats(far, pct, comp)
    assert st["rank"] == comp.shape[0] + 1 and cb.verdict(st) == "FAIL"
    assert st["gap_db"]["p50"] == pytest.approx(5.0, abs=0.1)


def test_peer_test_tolerance_follows_company_spread():
    # the same 1 dB offset passes against widely spread companies and
    # does not pass against companies that agree to 0.1 dB
    pct, wide, _ = _companies(spread=2.0)
    _, tight, _ = _companies(spread=0.1)
    u = np.random.default_rng(2).random(20000) * 100
    st_wide = cb.peer_stats(np.interp(u, pct, wide.mean(axis=0)) + 1.0, pct, wide)
    st_tight = cb.peer_stats(np.interp(u, pct, tight.mean(axis=0)) + 1.0, pct, tight)
    assert cb.verdict(st_wide) == "PASS"
    assert cb.verdict(st_tight) == "FAIL"


def test_combine():
    assert cb.combine(["PASS", "PASS"]) == "PASS"
    assert cb.combine(["PASS", "WARN"]) == "WARN"
    assert cb.combine(["WARN", "FAIL", "PASS"]) == "FAIL"


def test_dense_urban_calibration_drop():
    cfg = get_preset("rp-du-4g", ue_per_cell=2)
    assert len(cfg.calib_beams) == 12
    d = generate_drop(cfg, np.random.default_rng(3))
    idx = np.arange(d.ues.n)
    s = d.serving_cell
    # serving on the best beam: the geometry with random-beam interferers
    # differs from the best-beam-everywhere SINR, and is finite
    assert np.all(np.isfinite(d.geometry_db))
    p = 10 ** (d.rx_power_dbm / 10)
    best_everywhere = 10 * np.log10(p[s, idx] / (p.sum(axis=0) - p[s, idx]
                                                 + 10 ** (d.noise_dbm / 10)))
    assert np.mean(d.geometry_db) > np.mean(best_everywhere)
    # a 4 x 8 sub-array with 12 beams: the serving gain beats one element
    no_beams = dataclasses.replace(cfg, calib_beams=())
    d0 = generate_drop(no_beams, np.random.default_rng(3))
    assert np.median(d.serving_coupling_gain_db) > np.median(d0.serving_coupling_gain_db)


def test_calib_beams_needs_multipath():
    with pytest.raises(ValueError):
        get_preset("rp-du-4g", coupling_model="los")
