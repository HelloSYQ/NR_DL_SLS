"""MU-MIMO: zero-forcing on reported precoders and greedy UT pairing.

The gNB only knows what the UTs report: per sub-band a rank-r_u precoder
V_u (the PMI, unit-norm columns) and the SU CQI, i.e. the per-layer SINR
s_u the UT expects when it is served alone with r_u layers at full power.
For a co-scheduled set G on one RBG with L = sum_{u in G} r_u layers:

  * precoder: zero forcing on the stacked reported vectors V = [V_u ...],
    W = V (V^H V + delta I)^-1 with unit-norm columns, each layer at power
    1/L (total transmit power fixed);
  * MU SINR estimate of layer l of UT u: s_u * (r_u / L) * rho_l, where
    rho_l = |v_l^H w_l|^2 is the ZF projection loss (1 for orthogonal
    reports) and r_u / L the power split relative to SU;
  * pairing: the PF owner of the RBG opens the set; UTs are added greedily
    while the PF metric sum_{u, l} log2(1 + SINR_ul) / R_u grows, up to
    ``max_ues`` UTs and ``max_layers`` layers.  A UT alone gets
    r_u log2(1 + s_u) / R_u, the SU PF metric of the scheduler.  In a set
    of two or more the per-UT SINR ``s_mu`` is used instead: the caller
    applies the UT's MU OLLA back-off (relative to its SU one) there, so
    UTs whose MU transmissions fail are paired less.
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


def _set_metric(rho, s_lin, r, n_layers, pf):
    """PF metric of sets, per-layer arrays (..., L) -> (...,)."""
    return np.sum(np.log2(1 + s_lin * r / n_layers * rho) / pf, axis=-1)


def greedy_pairing(owner: int, pool, v: dict, s_lin: dict, rank: dict,
                   pf: dict, max_ues: int, max_layers: int, s_mu: dict | None = None):
    """Co-scheduled set of one RBG.

    ``v[u]`` (S, r_u) unit columns, ``s_lin[u]`` SU per-layer SINR, ``s_mu[u]``
    the one used in MU sets (default ``s_lin``), ``rank``, ``pf`` (average
    rate) per UT.  Returns (UTs in layer order, W (S, L) unit columns,
    per-layer MU SINR estimates (L,), UT of every layer (L,))."""
    s_mu = s_lin if s_mu is None else s_mu
    group = [owner]

    def layers(g):
        s_of = s_lin if len(g) == 1 else s_mu
        uid = np.concatenate([[u] * rank[u] for u in g])
        return (uid, np.array([s_of[u] for u in uid]),
                np.array([rank[u] for u in uid], float),
                np.array([pf[u] for u in uid]))

    uid, s, r, p = layers(group)
    best = _set_metric(np.ones(len(uid)), s, r, len(uid), p)
    s_g = np.array([s_mu[u] for u in uid])        # the group's SINRs once paired
    w, rho = v[owner], np.ones(len(uid))
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
            wb, rhob = zf(vb)
            n_new = n_l + rc
            s_b = np.concatenate([np.broadcast_to(s_g, (len(cu), n_l)),
                                  np.repeat([[s_mu[u]] for u in cu], rc, axis=1)], 1)
            r_b = np.concatenate([np.broadcast_to(r, (len(cu), n_l)),
                                  np.full((len(cu), rc), float(rc))], 1)
            p_b = np.concatenate([np.broadcast_to(p, (len(cu), n_l)),
                                  np.repeat([[pf[u]] for u in cu], rc, axis=1)], 1)
            m = _set_metric(rhob, s_b, r_b, n_new, p_b)
            i = int(np.argmax(m))
            if top is None or m[i] > top[0]:
                top = (m[i], cu[i], wb[i], rhob[i])
        if top[0] <= best:
            break
        best, u_new, w, rho = top
        group.append(u_new)
        uid, s, r, p = layers(group)
        s_g = s
    n_l = len(uid)
    return group, w, s * r / n_l * rho, uid
