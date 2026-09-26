"""Link budget: noise power, coupling gain, received power and geometry.

Coupling gain of cell c at UT u (the negative of the 3GPP "coupling loss"):

    CG[c, u] = G_BS,c(LOS direction) + G_UT - PL_b - SF - L_O2I - L_car  [dB]

with the BS gain of the port-0 TXRU toward the geometric LOS direction and
no fast fading (large-scale calibration, TR 38.901 clause 7.8.1).  Every cell
transmits at full power, so the geometry (wideband SINR) of a UT is

    G_u = P CG[s(u), u] / (sum_{c != s(u)} P CG[c, u] + N).
"""

from __future__ import annotations

import numpy as np

THERMAL_NOISE_DBM_HZ = -174.0


def db2lin(x):
    return 10.0 ** (np.asarray(x, float) / 10.0)


def lin2db(x):
    return 10.0 * np.log10(np.maximum(np.asarray(x, float), 1e-300))


def noise_power_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    return THERMAL_NOISE_DBM_HZ + 10.0 * np.log10(bandwidth_hz) + noise_figure_db


def rsrp_dbm(tx_power_dbm: float, n_rb: int, coupling_gain_db):
    """RSRP: received power per resource element [dBm]."""
    return tx_power_dbm - 10.0 * np.log10(12 * n_rb) + np.asarray(coupling_gain_db)


def geometry_db(rx_power_dbm: np.ndarray, serving: np.ndarray,
                noise_dbm: float) -> np.ndarray:
    """Wideband SINR of each UT from the (C, U) received powers [dB]."""
    p = db2lin(rx_power_dbm)
    idx = np.arange(p.shape[1])
    s = p[serving, idx]
    i = p.sum(axis=0) - s
    return lin2db(s / (i + db2lin(noise_dbm)))
