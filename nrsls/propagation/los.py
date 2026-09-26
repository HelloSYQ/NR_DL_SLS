"""LOS probability, TR 38.901 Table 7.4.2-1.

For O2I UTs the LOS probability is evaluated with the outdoor distance
d2D-out = d2D - d2D-in; the LOS state then describes the outdoor part of the
link (it selects the LOS or NLOS basic pathloss).  InH uses d2D directly.
"""

from __future__ import annotations

import numpy as np


def los_probability(scenario: str, d2d_out, h_ut=1.5):
    d = np.asarray(d2d_out, float)
    fam = scenario.split("-")[0].lower()
    if fam == "rma":
        return np.where(d <= 10.0, 1.0, np.exp(-(d - 10.0) / 1000.0))
    if fam == "umi":
        ds = np.maximum(d, 18.0)
        p = 18.0 / ds + np.exp(-ds / 36.0) * (1.0 - 18.0 / ds)
        return np.where(d <= 18.0, 1.0, p)
    if fam == "uma":
        h = np.broadcast_to(np.asarray(h_ut, float), d.shape)
        c = np.where(h <= 13.0, 0.0,
                     ((np.maximum(h, 13.0) - 13.0) / 10.0) ** 1.5)
        ds = np.maximum(d, 18.0)
        p = ((18.0 / ds + np.exp(-ds / 63.0) * (1.0 - 18.0 / ds))
             * (1.0 + c * 1.25 * (ds / 100.0) ** 3 * np.exp(-ds / 150.0)))
        return np.where(d <= 18.0, 1.0, p)
    if scenario == "InH-mixed":
        return np.where(d <= 1.2, 1.0,
                        np.where(d < 6.5, np.exp(-(d - 1.2) / 4.7),
                                 0.32 * np.exp(-(d - 6.5) / 32.6)))
    if scenario == "InH-open":
        return np.where(d <= 5.0, 1.0,
                        np.where(d <= 49.0, np.exp(-(d - 5.0) / 70.8),
                                 0.54 * np.exp(-(d - 49.0) / 211.7)))
    raise ValueError(f"no LOS probability for scenario {scenario!r}")
