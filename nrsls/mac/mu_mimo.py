"""MU-MIMO: zero-forcing on reported precoders and greedy UT pairing.

The gNB only knows what the UTs report: per sub-band a rank-r_u precoder
V_u (the PMI, unit-norm columns) and the SU CQI, i.e. the per-layer SINR
s_u the UT expects when it is served alone with r_u layers at full power.
For a co-scheduled set G on one RBG with L = sum_{u in G} r_u layers:

  * precoder: zero forcing on the stacked reported vectors V = [V_u ...],
    W = V (V^H V + delta I)^-1, or regularised ZF on the SINR-scaled
    reports (``mu_precode``), unit-norm columns, each layer at power 1/L
    (total transmit power fixed);
  * MU SINR estimate of layer l of UT u: s_u * (r_u / L) * rho_l, where
    rho_l = |v_l^H w_l|^2 is the ZF projection loss (1 for orthogonal
    reports) and r_u / L the power split relative to SU;
  * pairing: the PF owner of the RBG opens the set; UTs are added greedily
    while the PF metric sum_{u, l} log2(1 + SINR_ul) / R_u grows, up to
    ``max_ues`` UTs and ``max_layers`` layers.  A UT alone gets
    r_u log2(1 + s_u) / R_u, the SU PF metric of the scheduler.  In a set
    of two or more the per-UT SINR ``s_mu`` is used instead: the caller
    applies the UT's MU OLLA back-off (relative to its SU one) there, so
    UTs whose MU transmissions fail are paired less.  A set with more than
    ``dd_layers`` layers pays the extra DM-RS overhead: its metric is scaled
    by ``dd_factor`` (the data REs left with double-symbol DM-RS).
"""

from __future__ import annotations

import numpy as np

ZF_DELTA = 1e-3          # regularisation of V^H V (near-parallel reports)


def unit_columns(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-2, keepdims=True), 1e-12)


def zf(v: np.ndarray, delta: float = ZF_DELTA):
    """Zero forcing on unit-column V (..., S, L) -> (W with unit-norm
    columns (..., S, L), projection gains rho (..., L))."""
    n_l = v.shape[-1]
    vh = np.conj(np.swapaxes(v, -1, -2))
    w = v @ np.linalg.inv(vh @ v + delta * np.eye(n_l))
    w = unit_columns(w)
    rho = np.abs(np.einsum("...sl,...sl->...l", np.conj(v), w)) ** 2
    return w, rho


def mu_precode(v: np.ndarray, s_full: np.ndarray, method: str = "zf"):
    """MU precoder and per-layer SINR estimates from the reports.

    ``v`` (..., S, L) unit-column reported precoders, ``s_full`` (..., L) the
    per-layer SNR a layer would get at full power (SU CQI SINR x its UT's
    rank).  The gNB's channel model of layer l is g_l = sqrt(s_full_l) v_l
    with unit noise; every layer gets power 1/L.

      * 'zf':  W = V (V^H V + delta I)^-1, SINR_l = s_full_l rho_l / L;
      * 'rzf': regularised ZF (MMSE precoder) W = G^H (G G^H + L I)^-1,
        which tends to ZF at high SNR and to matched filtering at low SNR;
        SINR_l = (|g_l^H w_l|^2 / L) / (1 + sum_{j != l} |g_l^H w_j|^2 / L).

    Returns (W (..., S, L) unit columns, SINR (..., L))."""
    n_l = v.shape[-1]
    if method == "zf":
        w, rho = zf(v)
        return w, s_full * rho / n_l
    if method != "rzf":
        raise ValueError(f"unknown MU precoder {method!r}")
    gh = v * np.sqrt(s_full)[..., None, :]                   # G^H (..., S, L)
    g = np.conj(np.swapaxes(gh, -1, -2))                     # G   (..., L, S)
    w = unit_columns(gh @ np.linalg.inv(g @ gh + n_l * np.eye(n_l)))
    p = np.abs(g @ w) ** 2 / n_l                             # |g_l^H w_j|^2 / L
    sig = np.diagonal(p, axis1=-2, axis2=-1)
    return w, sig / (1 + p.sum(axis=-1) - sig)


def _metric(sinr, pf, n_layers, dd_layers=8, dd_factor=1.0):
    """PF metric of sets, per-layer arrays (..., L) -> (...,)."""
    m = np.sum(np.log2(1 + sinr) / pf, axis=-1)
    return m * (dd_factor if n_layers > dd_layers else 1.0)


def greedy_pairing(owner, pool, v: dict, s_lin: dict, rank: dict,
                   pf: dict, max_ues: int, max_layers: int, s_mu: dict | None = None,
                   dd_layers: int = 4, dd_factor: float = 1.0, method: str = "zf"):
    """Co-scheduled set of one RBG.

    ``owner``: the UT (or list of UTs, e.g. retransmissions) that opens the
    set.  ``v[u]`` (S, r_u) unit columns, ``s_lin[u]`` SU per-layer SINR,
    ``s_mu[u]`` the one used in MU sets (default ``s_lin``), ``rank``, ``pf``
    (average rate) per UT, ``method`` the MU precoder ('zf' or 'rzf', see
    :func:`mu_precode`).  Returns (UTs in layer order, W (S, L) unit
    columns, per-layer MU SINR estimates (L,), UT of every layer (L,))."""
    s_mu = s_lin if s_mu is None else s_mu
    group = list(owner) if isinstance(owner, (list, tuple)) else [owner]

    def layers(g):
        s_of = s_lin if len(g) == 1 else s_mu
        uid = np.concatenate([[u] * rank[u] for u in g])
        return (uid, np.array([s_of[u] for u in uid]),
                np.array([rank[u] for u in uid], float),
                np.array([pf[u] for u in uid]))

    uid, s, r, p = layers(group)
    if len(group) == 1:
        w, sinr = v[group[0]], s
    else:
        w, sinr = mu_precode(np.concatenate([v[u] for u in group], axis=1), s * r, method)
    best = _metric(sinr, p, len(uid), dd_layers, dd_factor)
    s_g = np.array([s_mu[u] for u in uid])        # the group's SINRs once paired
    while len(group) < max_ues:
        n_l = len(uid)
        cands = [u for u in pool if u not in group and n_l + rank[u] <= max_layers]
        if not cands:
            break
        v_g = np.concatenate([v[u] for u in group], axis=1)
        top = None
        for rc in sorted({rank[u] for u in cands}):          # batch per rank
            cu = [u for u in cands if rank[u] == rc]
            vb = np.stack([np.concatenate([v_g, v[u]], axis=1) for u in cu])
            n_new = n_l + rc
            s_b = np.concatenate([np.broadcast_to(s_g, (len(cu), n_l)),
                                  np.repeat([[s_mu[u]] for u in cu], rc, axis=1)], 1)
            r_b = np.concatenate([np.broadcast_to(r, (len(cu), n_l)),
                                  np.full((len(cu), rc), float(rc))], 1)
            p_b = np.concatenate([np.broadcast_to(p, (len(cu), n_l)),
                                  np.repeat([[pf[u]] for u in cu], rc, axis=1)], 1)
            wb, sb = mu_precode(vb, s_b * r_b, method)
            m = _metric(sb, p_b, n_new, dd_layers, dd_factor)
            i = int(np.argmax(m))
            if top is None or m[i] > top[0]:
                top = (m[i], cu[i], wb[i], sb[i])
        if top[0] <= best:
            break
        best, u_new, w, sinr = top
        group.append(u_new)
        uid, s, r, p = layers(group)
        s_g = s
    return group, w, sinr, uid
