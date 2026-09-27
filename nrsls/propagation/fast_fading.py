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


# ----------------------------------------------------------------------------
# Batched, cluster-collapsed channel synthesis (phase 3)
# ----------------------------------------------------------------------------

# one-hot map of the 20 rays onto the 3 sub-clusters (Table 7.5-5)
_SUB_ONEHOT = np.eye(3, dtype=np.float32)[_RAY_SUB]            # (M, 3)


def subset_clusters(cl: Clusters, idx, dtype=np.float32) -> Clusters:
    """Clusters of the links ``idx`` only, with ray angles/phases in ``dtype``."""
    idx = np.asarray(idx)
    return Clusters(
        valid=cl.valid[idx], power=cl.power[idx].astype(dtype),
        delay_s=cl.delay_s[idx], aoa=cl.aoa[idx].astype(dtype),
        aod=cl.aod[idx].astype(dtype), zoa=cl.zoa[idx].astype(dtype),
        zod=cl.zod[idx].astype(dtype), kappa=cl.kappa[idx].astype(dtype),
        phase=cl.phase[idx].astype(dtype), k_r=cl.k_r[idx],
        los_aod=cl.los_aod[idx], los_zod=cl.los_zod[idx],
        los_aoa=cl.los_aoa[idx], los_zoa=cl.los_zoa[idx], c_ds_s=cl.c_ds_s[idx])


def concat_clusters(parts) -> Clusters:
    return Clusters(**{f: np.concatenate([getattr(p, f) for p in parts])
                       for f in Clusters.__dataclass_fields__})


def _tx_scalar_and_slants(cfg: BSAntennaConfig, bearing, az, zen):
    """Per-ray tx amplitude (element sqrt-gain x complex sub-array factor)
    and the GCS polarisation angle of each port slant.

    For panels without mechanical tilt the LCS is a pure azimuth rotation, so
    the field of a port with slant zeta is s * (cos zeta, sin zeta).
    """
    az_l = az - bearing[:, None, None]
    af = _subarray_factor(cfg, az_l, zen)
    if cfg.pattern == "omni":
        g = np.ones(az.shape)
    else:
        from nrdlsim.channel_models import local_element_gain
        g = local_element_gain(az_l, zen, cfg.max_gain_dbi, cfg.hpbw_deg,
                               cfg.front_back_db)
    return np.sqrt(g) * af


def channel_batch(cl: Clusters, bearing_deg, bs_cfg: BSAntennaConfig,
                  ue: UEAntenna, freqs_hz, t_s: float, velocity_mps,
                  wavelength_m: float, d3d_m):
    """H[l, f, u, s] for L links at time ``t_s`` (antenna + multipath only).

    Same model as :func:`link_channel`, evaluated per sub-cluster: the rays
    of a sub-cluster share one delay, so they are first summed (with their
    Doppler phases) into a U x S matrix, and H(f) is a sum over at most
    3 N sub-clusters.  The port location phases are separable over the
    horizontal / vertical TXRU grid, so only Np + Mp exponentials are
    evaluated per ray.
    """
    bearing = np.asarray(bearing_deg, float)
    n_links = len(bearing)
    pos_u, sl_u = ue_port_layout(ue)
    k_v, l_h = bs_cfg.M // bs_cfg.Mp, bs_cfg.N // bs_cfg.Np
    slants = np.deg2rad([45.0, -45.0]) if bs_cfg.P == 2 else np.array([0.0])
    az, zen = cl.aod.astype(np.float32), cl.zod.astype(np.float32)   # (L, N, M)
    tilt = bs_cfg.mechanical_downtilt_deg
    # --- per-ray tx field of a +/-45 (or 0) deg element x sub-array factor ---
    if tilt == 0.0:
        scal = _tx_scalar_and_slants(bs_cfg, bearing, az, zen)       # (L, N, M)
        f_pol = [(scal * np.cos(z), scal * np.sin(z)) for z in slants]
    else:
        f_pol = [[np.empty(az.shape, complex), np.empty(az.shape, complex)]
                 for _ in slants]
        for b in np.unique(bearing):
            m = bearing == b
            R = rotation_matrix(b, tilt, 0.0)
            F, _ = element_field(az[m], zen[m], slants, R, bs_cfg.pattern,
                                 bs_cfg.max_gain_dbi, bs_cfg.hpbw_deg,
                                 bs_cfg.front_back_db)
            az_l, zen_l = to_local_angles(az[m], zen[m], R)
            af = _subarray_factor(bs_cfg, az_l, zen_l)
            for i in range(len(slants)):
                f_pol[i][0][m] = F[..., i, 0] * af
                f_pol[i][1][m] = F[..., i, 1] * af
    # --- separable port location phases (LCS y = horizontal, z = vertical) ---
    r_tx = _dir_cosines(az, zen)                                     # (L, N, M, 3)
    rot = np.stack([rotation_matrix(b, tilt, 0.0) for b in bearing])  # (L, 3, 3)
    r_loc = np.einsum("lnmi,lij->lnmj", r_tx, rot)                   # R^T r
    eh = np.exp(2j * np.pi * r_loc[..., 1:2] * (np.arange(bs_cfg.Np) * l_h * bs_cfg.dH))
    ev = np.exp(2j * np.pi * r_loc[..., 2:3] * (np.arange(bs_cfg.Mp) * k_v * bs_cfg.dV))
    loc = (eh[..., :, None] * ev[..., None, :]).reshape(az.shape + (-1,))
    loc = loc.astype(np.complex64)                                   # (L, N, M, Np Mp)
    # --- polarisation coupling -> A_theta, A_phi per port ---
    e = np.exp(1j * cl.phase.astype(np.float32))
    ik = 1 / np.sqrt(cl.kappa.astype(np.float32))
    a_t, a_p = [], []
    for ft, fp in f_pol:
        a_t.append(((e[..., 0] * ft + ik * e[..., 1] * fp)[..., None] * loc))
        a_p.append(((ik * e[..., 2] * ft + e[..., 3] * fp)[..., None] * loc))
    a_t = np.concatenate(a_t, -1).astype(np.complex64)               # (L, N, M, S)
    a_p = np.concatenate(a_p, -1).astype(np.complex64)
    # --- rx and Doppler ---
    aoa, zoa = cl.aoa.astype(np.float32), cl.zoa.astype(np.float32)
    r_rx = _dir_cosines(aoa, zoa)
    loc_u = np.exp(2j * np.pi * (r_rx @ pos_u.T))                    # (L, N, M, U)
    v = np.asarray(velocity_mps, float).reshape(n_links, 3)
    dop = np.exp(2j * np.pi * np.einsum("lnmi,li->lnm", r_rx, v) / wavelength_m * t_s)
    amp = np.sqrt(np.where(cl.valid, cl.power, 0.0) / N_RAYS)[..., None] * dop
    w = (amp[..., None] * loc_u).astype(np.complex64)                 # (L, N, M, U)
    # sub-cluster sums as batched matmuls: (U, M) @ (M, S) per (l, n, k)
    wk = np.swapaxes(w, -1, -2)[:, :, None] * _SUB_ONEHOT.T[None, None, :, None, :]
    c3 = (np.cos(sl_u)[:, None] * (wk @ a_t[:, :, None])
          + np.sin(sl_u)[:, None] * (wk @ a_p[:, :, None]))          # (L, N, 3, U, S)
    n_s = a_t.shape[-1]
    # --- delays of the sub-clusters ---
    p = np.where(cl.valid, cl.power, -1.0)
    strongest = np.argsort(p, axis=1)[:, ::-1][:, :2]
    is_strong = np.zeros(cl.valid.shape, bool)
    np.put_along_axis(is_strong, strongest, True, axis=1)
    tau = (cl.delay_s[..., None] + is_strong[..., None] * np.arange(3)
           * 1.28 * cl.c_ds_s[:, None, None])                     # (L, N, 3)
    f = np.asarray(freqs_hz, float)
    ph = np.exp(-2j * np.pi * f[None, :, None] * tau.reshape(n_links, 1, -1))
    n_u = len(sl_u)
    h = ph.astype(np.complex64) @ c3.reshape(n_links, -1, n_u * n_s)                     # (L, F, U*S)
    h = h.reshape(n_links, len(f), n_u, n_s) / np.sqrt(cl.k_r + 1)[:, None, None, None]
    # --- LOS ray ---
    los = np.nonzero(cl.k_r > 0)[0]
    for l in los:
        txl = bs_response(bs_cfg, bearing[l], np.array(cl.los_aod[l]),
                          np.array(cl.los_zod[l]))
        rxl = ue_response(ue, np.array(cl.los_aoa[l]), np.array(cl.los_zoa[l]))
        hl = np.einsum("ua,sa->us", rxl, np.stack([txl[..., 0], -txl[..., 1]], -1))
        fdl = _dir_cosines(cl.los_aoa[l], cl.los_zoa[l]) @ v[l] / wavelength_m
        hl = hl * np.exp(-2j * np.pi * d3d_m[l] / wavelength_m + 2j * np.pi * fdl * t_s)
        k = cl.k_r[l]
        h[l] += np.sqrt(k / (k + 1)) * hl[None]
    return h.astype(np.complex64)
