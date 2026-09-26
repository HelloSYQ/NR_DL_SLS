"""Comparison of simulated CDFs against reference calibration curves.

Reference curves (e.g. the per-company or average results of the 3GPP
TR 38.901 clause 7.8 calibration campaign) are read from a two-column CSV
file ``x, cdf`` with cdf in [0, 1].  The comparison reports the horizontal
gap (simulated minus reference, in the unit of x) at fixed percentiles,
which is how calibration agreement is normally quoted ("within 1 dB").
"""

from __future__ import annotations

import numpy as np

from .kpi import ecdf

GAP_PERCENTILES = (5, 10, 20, 50, 80, 90, 95)


def load_reference_csv(path: str):
    data = np.loadtxt(path, delimiter=",", comments="#")
    x, f = data[:, 0], data[:, 1]
    order = np.argsort(f)
    return x[order], f[order]


def percentile_gaps(samples, ref_x, ref_cdf, pct=GAP_PERCENTILES) -> dict:
    """Simulated minus reference value at each percentile."""
    sim = np.percentile(np.asarray(samples, float), pct)
    ref = np.interp(np.asarray(pct) / 100.0, ref_cdf, ref_x)
    return {f"p{p:g}": float(s - r) for p, s, r in zip(pct, sim, ref)}


def max_abs_gap(samples, ref_x, ref_cdf, pct=GAP_PERCENTILES) -> float:
    return max(abs(v) for v in percentile_gaps(samples, ref_x, ref_cdf,
                                               pct).values())


def ks_distance(a, b) -> float:
    """Two-sample Kolmogorov-Smirnov distance between sample sets a and b."""
    xa, fa = ecdf(a)
    xb, fb = ecdf(b)
    grid = np.concatenate([xa, xb])
    ca = np.searchsorted(xa, grid, side="right") / len(xa)
    cb = np.searchsorted(xb, grid, side="right") / len(xb)
    return float(np.max(np.abs(ca - cb)))
