"""Small-scale parameters: clusters and rays, TR 38.901 clause 7.5 steps 5-10.

For a set of links with known LSPs and LOS geometry this draws

  5. cluster delays  tau'_n = -r_tau DS ln(X_n), sorted and shifted to 0
     (LOS: also the K-scaled delays tau_n / C_tau, eq. 7.5-3/4);
  6. cluster powers  P'_n = exp(-tau_n (r_tau - 1) / (r_tau DS)) 10^(-Z_n/10),
     Z_n ~ N(0, zeta^2), normalised (eq. 7.5-5/6).  Clusters more than 25 dB
     below the strongest are removed.  LOS links use the K-scaled powers of
     eq. 7.5-8 (specular part added to the first cluster) for the angles;
  7. arrival / departure angles (eq. 7.5-9 ... 7.5-20): wrapped-Gaussian
     azimuths, Laplacian zeniths, random sign X_n, fluctuation Y_n, the LOS
     re-alignment of the first cluster, the ZOD offset, and the 20 ray offsets
     of Table 7.5-3 scaled by c_ASA, c_ASD, c_ZSA and (3/8) 10^mu_lgZSD;
  8. random coupling of the rays of AOD/AOA, ZOD/ZOA and AOD/ZOD;
  9. per-ray cross-polarisation ratios kappa = 10^(X/10), X ~ N(mu, sigma^2);
 10. random initial phases for the four polarisation combinations.

The two strongest clusters' sub-cluster split (step 11) only regroups ray
delays; it is applied when the channel coefficients are built.
O2I links use the O2I parameters and have no LOS component; their mean
arrival zenith is 90 deg.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .lsp_tables import PARAMS
from .pathloss import LOS, NLOS, O2I

# Table 7.5-3: ray offset angles within a cluster (unit RMS spread)
RAY_OFFSETS = np.array([0.0447, -0.0447, 0.1413, -0.1413, 0.2492, -0.2492,
                        0.3715, -0.3715, 0.5129, -0.5129, 0.6797, -0.6797,
                        0.8844, -0.8844, 1.1481, -1.1481, 1.5195, -1.5195,
                        2.1551, -2.1551])
N_RAYS = len(RAY_OFFSETS)


@dataclass
class Clusters:
    """Clusters and rays of L links (padded to the largest cluster count N)."""

    valid: np.ndarray        # (L, N) cluster exists (not pruned / padding)
    power: np.ndarray        # (L, N) NLOS cluster powers, sum 1 per link
    delay_s: np.ndarray      # (L, N) cluster delays (K-scaled for LOS links)
    aoa: np.ndarray          # (L, N, M) ray angles [deg], coupled
    aod: np.ndarray
    zoa: np.ndarray
    zod: np.ndarray
    kappa: np.ndarray        # (L, N, M) linear XPR
    phase: np.ndarray        # (L, N, M, 4) initial phases (tt, tp, pt, pp)
    k_r: np.ndarray          # (L,) linear Ricean K (0 for NLOS / O2I links)
    los_aod: np.ndarray      # (L,) LOS angles [deg]
    los_zod: np.ndarray
    los_aoa: np.ndarray
    los_zoa: np.ndarray
    c_ds_s: np.ndarray       # (L,) cluster delay spread (sub-clusters)


def _wrap_zenith(z):
    z = np.mod(z, 360.0)
    return np.where(z > 180.0, 360.0 - z, z)


def _c_tau(k_db):
    return 0.7705 - 0.0433 * k_db + 0.0002 * k_db ** 2 + 0.000017 * k_db ** 3


def generate_clusters(family, fc_ghz, condition, lsps, los_aod, los_zod,
                      rng) -> Clusters:
    """Clusters and rays for L links.

    ``condition`` (L,) holds LOS / NLOS / O2I; ``lsps`` is an object with
    (L,)-shaped ``k_db, ds_s, asd_deg, asa_deg, zsd_deg, zsa_deg, mu_lg_zsd,
    zod_offset_deg``; ``los_aod`` / ``los_zod`` are the geometric departure
    angles (the arrival ones follow).
    """
    cond = np.asarray(condition)
    n_links = len(cond)
    los = cond == LOS
    fc_cd = max(fc_ghz, 1e-9)
    per = [PARAMS[family][c] for c in (LOS, NLOS, O2I) if c in PARAMS[family]]
    n_max = max(p["n_clusters"] for p in per)

    def col(key, idx=None):
        """Per-link parameter from each link's condition table."""
        out = np.zeros(n_links)
        for c in (LOS, NLOS, O2I):
            m = cond == c
            if m.any():
                v = PARAMS[family][c][key]
                out[m] = v if idx is None else v[idx]
        return out

    n_cl = col("n_clusters").astype(int)
    r_tau, zeta = col("r_tau"), col("zeta")
    ds = lsps.ds_s
    k_db = np.where(los, lsps.k_db, 0.0)
    k_r = np.where(los, 10 ** (k_db / 10), 0.0)
    exists = np.arange(n_max)[None, :] < n_cl[:, None]

    # --- step 5: delays ---
    x = rng.random((n_links, n_max))
    tau = -r_tau[:, None] * ds[:, None] * np.log(np.maximum(x, 1e-300))
    tau = np.where(exists, tau, np.inf)
    tau = np.sort(tau - tau.min(axis=1, keepdims=True), axis=1)
    tau = np.where(exists, tau, 0.0)

    # --- step 6: powers ---
    z = zeta[:, None] * rng.standard_normal((n_links, n_max))
    p = (np.exp(-tau * (r_tau[:, None] - 1) / (r_tau[:, None] * ds[:, None]))
         * 10 ** (-z / 10))
    p = np.where(exists, p, 0.0)
    p /= p.sum(axis=1, keepdims=True)
    # K-scaled powers (eq. 7.5-8), used for the angles only
    p_ang = p / (k_r[:, None] + 1)
    p_ang[:, 0] += k_r / (k_r + 1)
    valid = exists & (p > p.max(axis=1, keepdims=True) * 10 ** (-2.5))
    p = np.where(valid, p, 0.0)
    p /= p.sum(axis=1, keepdims=True)
    delay = np.where(los[:, None], tau / _c_tau(k_db)[:, None], tau)

    # --- step 7: angles ---
    rel = np.where(valid, p_ang / p_ang.max(axis=1, keepdims=True), 1.0)
    rel = np.clip(rel, 1e-12, 1.0)
    c_phi = col("c_phi") * np.where(
        los, 1.1035 - 0.028 * k_db - 0.002 * k_db ** 2 + 0.0001 * k_db ** 3, 1.0)
    c_th = col("c_theta") * np.where(
        los, 1.3086 + 0.0339 * k_db - 0.0077 * k_db ** 2 + 0.0002 * k_db ** 3, 1.0)
    los_aoa = np.mod(los_aod + 180.0, 360.0)
    los_zoa = 180.0 - los_zod
    zoa_mean = np.where(cond == O2I, 90.0, los_zoa)

    def azimuths(spread, los_dir):
        base = 2 * (spread[:, None] / 1.4) * np.sqrt(-np.log(rel)) / c_phi[:, None]
        sgn = rng.choice([-1.0, 1.0], size=(n_links, n_max))
        y = (spread[:, None] / 7) * rng.standard_normal((n_links, n_max))
        a = sgn * base + y
        a = np.where(los[:, None], a - a[:, :1], a)     # first cluster on LOS
        return a + los_dir[:, None]

    def zeniths(spread, mean, offset):
        base = -spread[:, None] * np.log(rel) / c_th[:, None]
        sgn = rng.choice([-1.0, 1.0], size=(n_links, n_max))
        y = (spread[:, None] / 7) * rng.standard_normal((n_links, n_max))
        a = sgn * base + y
        a = np.where(los[:, None], a - a[:, :1], a + offset[:, None])
        return a + mean[:, None]

    aoa_c = azimuths(lsps.asa_deg, los_aoa)
    aod_c = azimuths(lsps.asd_deg, los_aod)
    zoa_c = zeniths(lsps.zsa_deg, zoa_mean, np.zeros(n_links))
    zod_c = zeniths(lsps.zsd_deg, los_zod, lsps.zod_offset_deg)

    # rays, with random coupling (step 8): AOD in table order, the others
    # permuted independently within each cluster
    def perm():
        return np.argsort(rng.random((n_links, n_max, N_RAYS)), axis=-1)

    off = RAY_OFFSETS[None, None, :]
    aod = aod_c[..., None] + col("c_asd")[:, None, None] * off
    aoa = aoa_c[..., None] + col("c_asa")[:, None, None] * RAY_OFFSETS[perm()]
    zoa = zoa_c[..., None] + col("c_zsa")[:, None, None] * RAY_OFFSETS[perm()]
    c_zsd = (3.0 / 8.0) * 10 ** lsps.mu_lg_zsd
    zod = zod_c[..., None] + c_zsd[:, None, None] * RAY_OFFSETS[perm()]

    # --- steps 9-10: XPR and initial phases ---
    kappa = 10 ** ((col("xpr", 0)[:, None, None] + col("xpr", 1)[:, None, None]
                    * rng.standard_normal((n_links, n_max, N_RAYS))) / 10)
    phase = rng.uniform(-np.pi, np.pi, (n_links, n_max, N_RAYS, 4))

    cds = np.maximum(col("c_ds", 0), col("c_ds", 1) - col("c_ds", 2)
                     * np.log10(fc_cd)) * 1e-9
    return Clusters(valid=valid, power=p, delay_s=delay,
                    aoa=np.mod(aoa + 180.0, 360.0) - 180.0,
                    aod=np.mod(aod + 180.0, 360.0) - 180.0,
                    zoa=_wrap_zenith(zoa), zod=_wrap_zenith(zod),
                    kappa=kappa, phase=phase, k_r=k_r,
                    los_aod=los_aod, los_zod=los_zod, los_aoa=los_aoa,
                    los_zoa=los_zoa, c_ds_s=cds)
