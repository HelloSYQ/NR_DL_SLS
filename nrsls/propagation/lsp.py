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
    "inh_a": (10.0, 6.0, None),
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


# ----------------------------------------------------------------------------
# Full LSP set (phase 2): SF, K, DS, ASD, ASA, ZSD, ZSA
# ----------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402

from .lsp_tables import LSP_ORDER, PARAMS  # noqa: E402

_FC_MIN_GHZ = {"uma": 6.0, "umi": 2.0, "inh": 6.0, "inh_a": 6.0, "rma": 0.0}


@dataclass
class LSPs:
    """Large-scale parameters per (site, UT) link, shape (S, U) each."""

    sf_db: np.ndarray
    k_db: np.ndarray            # Ricean K (meaningful for LOS links only)
    ds_s: np.ndarray            # RMS delay spread [s]
    asd_deg: np.ndarray
    asa_deg: np.ndarray
    zsd_deg: np.ndarray
    zsa_deg: np.ndarray
    mu_lg_zsd: np.ndarray       # mean of lg ZSD (sets the ZOD ray spread)
    zod_offset_deg: np.ndarray  # mu_offset,ZOD (Tables 7.5-7 ... 7.5-10)


def _lin(tab, fc):
    """mu or sigma = a log10(b + fc) + c."""
    a, b, c = tab
    return a * np.log10(b + fc) + c if a else c


def zsd_and_offset(family, outdoor_los, d2d, h_bs, h_ut, fc_ghz):
    """(mu_lgZSD, sigma_lgZSD, ZOD offset [deg]) per link, Tables 7.5-7..10."""
    los = np.asarray(outdoor_los, bool)
    d = np.asarray(d2d, float)
    fc = max(fc_ghz, _FC_MIN_GHZ[family])
    if family == "uma":
        base = -2.1 * d / 1000 - 0.01 * (h_ut - 1.5)
        mu = np.where(los, np.maximum(-0.5, base + 0.75),
                      np.maximum(-0.5, base + 0.9))
        sig = np.where(los, 0.40, 0.49)
        a = 0.208 * np.log10(fc) - 0.782
        c = -0.13 * np.log10(fc) + 2.03
        e = 7.66 * np.log10(fc) - 5.96
        off = e - 10 ** (a * np.log10(np.maximum(25.0, d)) + c - 0.07 * (h_ut - 1.5))
    elif family == "umi":
        mu = np.where(los,
                      np.maximum(-0.21, -14.8 * d / 1000 + 0.01 * np.abs(h_ut - h_bs) + 0.83),
                      np.maximum(-0.5, -3.1 * d / 1000
                                 + 0.01 * np.maximum(h_ut - h_bs, 0.0) + 0.2))
        sig = np.full(d.shape, 0.35)
        off = -10 ** (-1.5 * np.log10(np.maximum(10.0, d)) + 3.3)
    elif family == "rma":
        mu = np.where(los, np.maximum(-1.0, -0.17 * d / 1000 - 0.01 * (h_ut - 1.5) + 0.22),
                      np.maximum(-1.0, -0.19 * d / 1000 - 0.01 * (h_ut - 1.5) + 0.28))
        sig = np.where(los, 0.34, 0.30)
        off = np.rad2deg(np.arctan((35 - 3.5) / d) - np.arctan((35 - 1.5) / d))
    elif family == "inh_a":                   # M.2412 Table A1-17, <= 6 GHz
        mu = np.where(los, 1.02, 1.08)
        sig = np.where(los, 0.41, 0.36)
        off = np.zeros(d.shape)
    elif family == "inh":
        lf = np.log10(1 + fc)
        mu = np.where(los, -1.43 * lf + 2.228, 1.08)
        sig = np.where(los, 0.13 * lf + 0.30, 0.36)
        off = np.zeros(d.shape)
    else:
        raise ValueError(family)
    return (np.broadcast_to(mu, d.shape), np.broadcast_to(sig, d.shape),
            np.where(los, 0.0, np.broadcast_to(off, d.shape)))


def cross_corr_sqrt(xcorr: dict) -> np.ndarray:
    """Square root of the 7x7 LSP cross-correlation matrix (order LSP_ORDER)."""
    idx = {n: i for i, n in enumerate(LSP_ORDER)}
    c = np.eye(len(LSP_ORDER))
    for (a, b), v in xcorr.items():
        c[idx[a], idx[b]] = c[idx[b], idx[a]] = v
    return _sqrt_psd(c)


def draw_lsps(family, fc_ghz, condition, outdoor_los, d2d, h_bs, h_ut, sf_std_db,
              ue_xy, ue_floor, rng, spatial=True) -> LSPs:
    """All seven LSPs per (site, UT) link (TR 38.901 clause 7.5 step 4).

    For each link condition present, every LSP gets S independent site
    fields with the LSP's own correlation distance; the 7 fields are then
    mixed with the square root of the cross-correlation matrix and scaled by
    the log-normal statistics.  ``sf_std_db`` (S, U) carries the SF standard
    deviation (including the RMa breakpoint rule).
    """
    condition = np.asarray(condition)
    shape = condition.shape
    fc = max(fc_ghz, _FC_MIN_GHZ[family])
    mu_zsd, sig_zsd, off = zsd_and_offset(family, outdoor_los, d2d, h_bs, h_ut, fc_ghz)
    out = {k: np.zeros(shape) for k in ("sf", "k", "ds", "asd", "asa", "zsd", "zsa")}
    for cond in (LOS, NLOS, O2I):
        mask = condition == cond
        if not mask.any():
            continue
        p = PARAMS[family][cond]
        xi = np.stack([correlated_fields(shape[0], ue_xy, ue_floor, dc, rng, spatial)
                       for dc in p["corr_dist"]])                  # (7, S, U)
        s = np.einsum("ij,jsu->isu", cross_corr_sqrt(p["xcorr"]), xi)
        z = dict(zip(LSP_ORDER, s))
        vals = {
            "sf": np.asarray(sf_std_db) * z["SF"],
            "k": p["k"][0] + p["k"][1] * z["K"],
            "ds": 10 ** (_lin(p["ds"][:3], fc) + _lin(p["ds"][3:], fc) * z["DS"]),
            "asd": np.minimum(10 ** (_lin(p["asd"][:3], fc)
                                     + _lin(p["asd"][3:], fc) * z["ASD"]), 104.0),
            "asa": np.minimum(10 ** (_lin(p["asa"][:3], fc)
                                     + _lin(p["asa"][3:], fc) * z["ASA"]), 104.0),
            "zsa": np.minimum(10 ** (_lin(p["zsa"][:3], fc)
                                     + _lin(p["zsa"][3:], fc) * z["ZSA"]), 52.0),
            "zsd": np.minimum(10 ** (mu_zsd + sig_zsd * z["ZSD"]), 52.0),
        }
        for k in out:
            out[k] = np.where(mask, vals[k], out[k])
    return LSPs(sf_db=out["sf"], k_db=out["k"], ds_s=out["ds"], asd_deg=out["asd"],
                asa_deg=out["asa"], zsd_deg=out["zsd"], zsa_deg=out["zsa"],
                mu_lg_zsd=np.asarray(mu_zsd), zod_offset_deg=np.asarray(off))
