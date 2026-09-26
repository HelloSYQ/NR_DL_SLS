"""Port-0 RSRP from the multipath channel, TR 36.873 eq. (8.1-1).

The RP-180524 / TR 37.910 calibration attaches UTs and computes coupling
gain from the RSRP of port 0 summed over every ray:

    RSRP = PL^-1 SF^-1 [ 1/(K+1) sum_n P_n / M sum_m g_nm + K/(K+1) g_LOS ]

    g_nm = 1/U sum_u | F_rx,u^T [[e^{j Phi_tt}, kappa^-1/2 e^{j Phi_tp}],
                                 [kappa^-1/2 e^{j Phi_pt}, e^{j Phi_pp}]] F_tx,0 |^2

with F_tx,0 the polarised field of the port-0 TXRU (element pattern times
sub-array gain) at the ray's departure angles and F_rx,u the field of UT
port u at its arrival angles; the LOS ray uses [[1, 0], [0, -1]].  The array
phases drop out because each port is a single (virtual) antenna.  UT ports
are isotropic with 0 / 90 deg polarisation (P = 2) or 0 deg (P = 1).
"""

from __future__ import annotations

import numpy as np

from ..propagation.clusters import N_RAYS, Clusters


def _ue_power(v_t, v_p, ue_pol: int):
    """Mean power over the UT ports of the received field (v_theta, v_phi)."""
    if ue_pol == 2:
        return 0.5 * (np.abs(v_t) ** 2 + np.abs(v_p) ** 2)
    return np.abs(v_t) ** 2


def multipath_gain(cl: Clusters, port_field, ue_pol: int) -> np.ndarray:
    """Linear port-0 gain (antenna + multipath, no pathloss) per link, (L,).

    ``port_field(az, zen) -> (F_theta, F_phi)`` evaluates the BS port field
    at GCS departure angles of any shape.
    """
    ft, fp = port_field(cl.aod, cl.zod)                       # (L, N, M), real
    ft, fp = np.real(ft), np.real(fp)
    ik = 1.0 / cl.kappa
    cross = 2.0 * ft * fp / np.sqrt(cl.kappa)
    # |e^{jA} f_t + k^-1/2 e^{jB} f_p|^2 = f_t^2 + f_p^2 / k + 2 f_t f_p cos(A-B) / sqrt(k)
    g_t = ft ** 2 + ik * fp ** 2 + cross * np.cos(cl.phase[..., 0] - cl.phase[..., 1])
    if ue_pol == 2:
        g_p = ik * ft ** 2 + fp ** 2 + cross * np.cos(cl.phase[..., 2] - cl.phase[..., 3])
        g = 0.5 * (g_t + g_p)
    else:
        g = g_t
    nlos = np.sum(cl.power[..., None] * g, axis=(1, 2)) / N_RAYS
    lt, lp = port_field(cl.los_aod, cl.los_zod)
    g_los = _ue_power(lt, -lp, ue_pol)
    k = cl.k_r
    return nlos / (k + 1) + g_los * k / (k + 1)
