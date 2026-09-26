"""Channel coefficients H(f, t) of a link, TR 38.901 clause 7.5 steps 11-12.

For each ray (cluster n, ray m) of a link

    h_{u,s} = sqrt(P_n / M) F_rx,u^T [[e^{jPhi_tt}, kappa^-1/2 e^{jPhi_tp}],
                                      [kappa^-1/2 e^{jPhi_pt}, e^{jPhi_pp}]] F_tx,s
              * exp(j 2 pi r_rx . d_u) exp(j 2 pi r_tx . d_s) exp(j 2 pi r_rx . v t / lambda)

(eq. 7.5-22, positions in wavelengths), and the frequency response is
H_{u,s}(f, t) = sum over rays of h_{u,s} exp(-j 2 pi f tau).  The two
strongest clusters are split into three sub-clusters (rays 1-8, 19, 20 at
tau_n; 9-12, 17, 18 at tau_n + 1.28 c_DS; 13-16 at tau_n + 2.56 c_DS;
Table 7.5-5).  LOS links scale the NLOS part by sqrt(1/(K+1)) and add the
specular ray sqrt(K/(K+1)) with the [[1, 0], [0, -1]] polarisation matrix
(eq. 7.5-29/30).

Ports:
  * gNB: one per TXRU.  Port order is polarisation-major, then the
    horizontal TXRU index, then the vertical one:
    ``s = p * Np * Mp + n * Mp + m`` (the TS 38.214 codebook ordering with
    N1 = Np horizontal, N2 = Mp vertical).  A port's field is the element
    field times the complex sub-array factor, with its phase centre at the
    sub-array's first element;
  * UT: isotropic elements on an (M, N) grid, polarisation 0 / 90 deg,
    ordered the same way.

The returned H excludes pathloss, shadowing and penetration loss; scale it
by 10^(-(PL + SF + L_pen) / 20) for the absolute channel.
"""

from __future__ import annotations

import numpy as np

from nrdlsim.channel_models import (_dir_cosines, element_field,
                                    rotation_matrix, to_local_angles)

from ..config.scenario import BSAntennaConfig, UEAntenna
from .clusters import N_RAYS, Clusters

# Table 7.5-5: 0-based ray indices of the three sub-clusters
_SUB1 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 18, 19])
_SUB2 = np.array([8, 9, 10, 11, 16, 17])
_SUB3 = np.array([12, 13, 14, 15])
_RAY_SUB = np.zeros(N_RAYS, int)
_RAY_SUB[_SUB2], _RAY_SUB[_SUB3] = 1, 2


def bs_port_layout(cfg: BSAntennaConfig):
    """(positions [lambda], slants [rad]) of the TXRU phase centres (LCS)."""
    k, l = cfg.M // cfg.Mp, cfg.N // cfg.Np
    slants = np.deg2rad([45.0, -45.0]) if cfg.P == 2 else np.array([0.0])
    pos, sl = [], []
    for p in range(cfg.P):
        for n in range(cfg.Np):
            for m in range(cfg.Mp):
                pos.append([0.0, n * l * cfg.dH, m * k * cfg.dV])
                sl.append(slants[p])
    return np.array(pos), np.array(sl)


def ue_port_layout(ue: UEAntenna):
    slants = np.deg2rad([0.0, 90.0]) if ue.P == 2 else np.array([0.0])
    pos, sl = [], []
    for p in range(ue.P):
        for n in range(ue.N):
            for m in range(ue.M):
                pos.append([0.0, n * ue.dH, m * ue.dV])
                sl.append(slants[p])
    return np.array(pos), np.array(sl)


def _subarray_factor(cfg: BSAntennaConfig, az_l, zen_l):
    """Complex factor of one TXRU (K x L elements) relative to its first element."""
    k, l = cfg.M // cfg.Mp, cfg.N // cfg.Np
    th, ph = np.deg2rad(zen_l), np.deg2rad(az_l)
    tt = np.deg2rad(cfg.electrical_tilt_deg)
    pv = 2 * np.pi * cfg.dV * (np.cos(th) - np.cos(tt))
    ph_h = 2 * np.pi * cfg.dH * np.sin(th) * np.sin(ph)     # steered to az 0
    kk = np.arange(k)
    ll = np.arange(l)
    av = np.exp(1j * pv[..., None] * kk).sum(-1)
    ah = np.exp(1j * ph_h[..., None] * ll).sum(-1)
    return av * ah / np.sqrt(k * l)


def bs_response(cfg: BSAntennaConfig, bearing_deg, az, zen):
    """(..., S, 2) polarised port responses incl. location phases."""
    R = rotation_matrix(bearing_deg, cfg.mechanical_downtilt_deg, 0.0)
    pos, sl = bs_port_layout(cfg)
    F, _ = element_field(az, zen, sl, R, cfg.pattern, cfg.max_gain_dbi,
                         cfg.hpbw_deg, cfg.front_back_db)          # (..., S, 2)
    az_l, zen_l = to_local_angles(az, zen, R)
    af = _subarray_factor(cfg, az_l, zen_l)
    loc = np.exp(2j * np.pi * (_dir_cosines(az, zen) @ (pos @ R.T).T))
    return F * (af[..., None] * loc)[..., None]


def ue_response(ue: UEAntenna, az, zen):
    pos, sl = ue_port_layout(ue)
    F = np.stack([np.cos(sl), np.sin(sl)], -1) * np.ones(np.shape(az) + (1, 1))
    loc = np.exp(2j * np.pi * (_dir_cosines(az, zen) @ pos.T))
    return F * loc[..., None]


def link_channel(cl: Clusters, link: int, bs_cfg: BSAntennaConfig,
                 bearing_deg: float, ue: UEAntenna, freqs_hz, times_s=(0.0,),
                 velocity_mps=(0.0, 0.0, 0.0), wavelength_m=1.0,
                 d3d_m: float = 0.0):
    """H[t, f, u, s] of one link (antenna + multipath, no pathloss)."""
    v = cl.valid[link]
    n_idx = np.nonzero(v)[0]
    p = cl.power[link, n_idx]
    tau = cl.delay_s[link, n_idx]
    strongest = n_idx[np.argsort(p)[::-1][:2]]
    aod, zod = cl.aod[link, n_idx], cl.zod[link, n_idx]            # (N, M)
    aoa, zoa = cl.aoa[link, n_idx], cl.zoa[link, n_idx]
    tx = bs_response(bs_cfg, bearing_deg, aod, zod)               # (N, M, S, 2)
    rx = ue_response(ue, aoa, zoa)                                # (N, M, U, 2)
    ik = 1 / np.sqrt(cl.kappa[link, n_idx])
    e = np.exp(1j * cl.phase[link, n_idx])
    # polarisation matrix times the tx field: (N, M, S, 2)
    pt = np.stack([e[..., 0, None] * tx[..., 0] + (ik * e[..., 1])[..., None] * tx[..., 1],
                   (ik * e[..., 2])[..., None] * tx[..., 0] + e[..., 3, None] * tx[..., 1]],
                  axis=-1)
    amp = np.sqrt(p / N_RAYS)[:, None]                              # (N, 1)
    coef = amp[..., None, None] * np.einsum("nmua,nmsa->nmus", rx, pt)
    # sub-cluster delays for the two strongest clusters
    sub = np.isin(n_idx, strongest)[:, None] * _RAY_SUB[None, :]
    tau_r = tau[:, None] + sub * 1.28 * cl.c_ds_s[link]            # (N, M)
    r_rx = _dir_cosines(aoa, zoa)                                   # (N, M, 3)
    fd = r_rx @ np.asarray(velocity_mps, float) / wavelength_m      # (N, M)
    k = cl.k_r[link]
    freqs = np.asarray(freqs_hz, float)
    out = []
    for t in np.atleast_1d(times_s):
        ph = np.exp(-2j * np.pi * (freqs[:, None] * tau_r.reshape(-1)[None, :]
                                   - fd.reshape(-1)[None, :] * t))  # (F, R)
        h = np.tensordot(ph, coef.reshape(-1, *coef.shape[2:]), axes=(1, 0))
        h = h / np.sqrt(k + 1)
        if k > 0:
            a_d, z_d = cl.los_aod[link], cl.los_zod[link]
            a_a, z_a = cl.los_aoa[link], cl.los_zoa[link]
            txl = bs_response(bs_cfg, bearing_deg, np.array(a_d), np.array(z_d))
            rxl = ue_response(ue, np.array(a_a), np.array(z_a))
            ptl = np.stack([txl[..., 0], -txl[..., 1]], -1)
            hl = np.einsum("ua,sa->us", rxl, ptl)
            fdl = _dir_cosines(a_a, z_a) @ np.asarray(velocity_mps, float) / wavelength_m
            hl = hl * np.exp(-2j * np.pi * d3d_m / wavelength_m) * np.exp(2j * np.pi * fdl * t)
            h = h + np.sqrt(k / (k + 1)) * hl[None]
        out.append(h)
    return np.stack(out)                                            # (T, F, U, S)
