"""Large-scale parameters (LSPs), TR 38.901 clause 7.5 step 4.

Phase 1 draws the shadow fading (SF); the other LSPs (K, DS, ASD, ASA, ZSD,
ZSA) and their cross-correlation are added in phase 2 on the same
spatially-correlated fields.

Rules applied (clause 7.5 step 4):
  * LSPs of links to different sites are independent; co-sited sectors share
    them (the SF is drawn per site, then indexed per cell);
  * each LSP is a spatially correlated Gaussian field over the UT positions
    with the exponential autocorrelation exp(-d / d_cor), where the
    correlation distance d_cor depends on the link condition
    (Table 7.5-6: separate LOS, NLOS and O2I fields);
  * UTs on different floors are uncorrelated.

The field is sampled exactly on the UT positions: the correlation matrix is
factorised (Cholesky) once per drop and condition and reused for all sites.
"""

from __future__ import annotations

import numpy as np

from .pathloss import LOS, NLOS, O2I

# SF correlation distance [m] (TR 38.901 Table 7.5-6): (LOS, NLOS, O2I)
SF_CORR_DIST_M = {
    "uma": (37.0, 50.0, 7.0),
    "umi": (10.0, 13.0, 7.0),
    "rma": (37.0, 120.0, 120.0),
    "inh": (10.0, 6.0, None),
}


def _sqrt_psd(c: np.ndarray) -> np.ndarray:
    """Matrix square root L (L L^T = C) of a correlation matrix."""
    try:
        return np.linalg.cholesky(c + 1e-10 * np.eye(len(c)))
    except np.linalg.LinAlgError:
        w, v = np.linalg.eigh(c)
        return v * np.sqrt(np.clip(w, 0.0, None))


def correlation_sqrt(xy: np.ndarray, group: np.ndarray, d_cor: float):
    """Square root of the exponential correlation matrix of the UT positions.

    UTs in different ``group`` (floor) are uncorrelated.
    """
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    c = np.exp(-d / d_cor) * (group[:, None] == group[None, :])
    return _sqrt_psd(c)


def correlated_fields(n_fields: int, xy, group, d_cor, rng, spatial=True):
    """``n_fields`` independent unit-variance fields on the UTs, (n_fields, U)."""
    w = rng.standard_normal((n_fields, len(xy)))
    if not spatial:
        return w
    return w @ correlation_sqrt(np.asarray(xy, float), np.asarray(group),
                                d_cor).T


def shadow_fading_db(family: str, condition, sigma_db, ue_xy, ue_floor, rng,
                     spatial=True):
    """SF [dB] per (site, UT) link.

    ``condition`` and ``sigma_db`` have shape (S, U).  Each condition present
    gets its own set of S site fields; each link reads the field of its site
    and condition at its UT.
    """
    condition = np.asarray(condition)
    n_sites, n_ue = condition.shape
    z = np.zeros((n_sites, n_ue))
    for cond in (LOS, NLOS, O2I):
        mask = condition == cond
        if not mask.any():
            continue
        d_cor = SF_CORR_DIST_M[family][cond]
        f = correlated_fields(n_sites, ue_xy, ue_floor, d_cor, rng, spatial)
        z = np.where(mask, f, z)
    return np.asarray(sigma_db) * z
