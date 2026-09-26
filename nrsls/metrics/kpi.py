"""Statistics helpers: empirical CDFs and percentile summaries."""

from __future__ import annotations

import numpy as np

PERCENTILES = (5, 10, 50, 90, 95)


def ecdf(samples):
    """(sorted values, cumulative probabilities) of an empirical CDF."""
    x = np.sort(np.asarray(samples, float).ravel())
    return x, np.arange(1, len(x) + 1) / len(x)


def percentiles(samples, pct=PERCENTILES) -> dict:
    v = np.percentile(np.asarray(samples, float), pct)
    return {f"p{p:g}": float(x) for p, x in zip(pct, v)}


def large_scale_summary(stats) -> dict:
    """Headline numbers of a large-scale (calibration) run."""
    return {
        "n_ut": int(len(stats.geometry_db)),
        "n_drops": int(len(np.unique(stats.drop))),
        "coupling_gain_db": percentiles(stats.coupling_gain_db),
        "geometry_db": percentiles(stats.geometry_db),
        "los_fraction_serving": float(np.mean(stats.los)),
        "o2i_fraction": float(np.mean(stats.o2i)),
        "mean_ut_per_cell": float(np.mean(stats.ue_per_cell)),
    }
