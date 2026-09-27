"""Fast-fading parameters, TR 38.901 Table 7.5-6 (UMa, UMi-Street Canyon,
RMa, InH-Office), per link condition LOS / NLOS / O2I.

Log-domain LSP statistics use the table's frequency dependence

    mu_lgX = a * log10(b + fc) + c,   sigma_lgX = a' * log10(b' + fc) + c'

with fc in GHz (b = 1 for UMi and InH; UMa / InH clip fc to >= 6 GHz, UMi to
>= 2 GHz).  DS in s, angles in deg, K / XPR / SF in dB.  The ZSD mean and the
ZOD offset are distance dependent (Tables 7.5-7 ... 7.5-10) and live in
:mod:`nrsls.propagation.lsp`.

Keys: ``ds, asd, asa, zsa`` = (a, b, c, a', b', c'); ``k``, ``xpr`` =
(mu, sigma); ``sf``, ``zsd_sigma``; ``n_clusters``, ``r_tau``, ``zeta``
(per-cluster shadowing, dB); ``c_asd, c_asa, c_zsa`` (cluster spreads, deg);
``c_ds`` = (a, b, c) of the cluster delay spread in ns,
max(a, b - c log10 fc); ``c_phi``, ``c_theta`` (the NLOS scaling factors
C_phi^NLOS, C_theta^NLOS for this cluster count, Tables 7.5-2 / 7.5-4);
``corr_dist`` (m) and ``xcorr`` (cross-correlations) in the LSP order
(SF, K, DS, ASD, ASA, ZSD, ZSA).

Values transcribed from TR 38.901 V16; cross-checked against the tables in
NVIDIA Sionna (sionna.phy.channel.tr38901, models/v16_1).
"""

LSP_ORDER = ("SF", "K", "DS", "ASD", "ASA", "ZSD", "ZSA")

PARAMS = {
    "uma": {
        0: dict(  # LoS
            ds=(-0.0963, 0.0, -6.955, 0.0, 0.0, 0.66),
            asd=(0.1114, 0.0, 1.06, 0.0, 0.0, 0.28),
            asa=(0.0, 0.0, 1.81, 0.0, 0.0, 0.2),
            zsa=(0.0, 0.0, 0.95, 0.0, 0.0, 0.16),
            k=(9.0, 3.5), xpr=(8.0, 4.0),
            sf=4.0, zsd_sigma=0.4, n_clusters=12, r_tau=2.5, zeta=3.0,
            c_ds=(0.25, 6.5622, 3.4084), c_asd=5.0, c_asa=11.0, c_zsa=7.0,
            c_phi=1.146, c_theta=1.104,
            corr_dist=(37.0, 12.0, 30.0, 18.0, 15.0, 15.0, 15.0),
            xcorr={("SF", "DS"): -0.4, ("SF", "ASD"): -0.5, ("SF", "ASA"): -0.5, ("SF", "ZSA"): -0.8, ("K", "DS"): -0.4, ("K", "ASA"): -0.2, ("DS", "ASD"): 0.4, ("DS", "ASA"): 0.8, ("DS", "ZSD"): -0.2, ("ASD", "ZSD"): 0.5, ("ASA", "ZSD"): -0.3, ("ASA", "ZSA"): 0.4}),
        1: dict(  # NLoS
            ds=(-0.204, 0.0, -6.28, 0.0, 0.0, 0.39),
            asd=(-0.1144, 0.0, 1.5, 0.0, 0.0, 0.28),
            asa=(-0.27, 0.0, 2.08, 0.0, 0.0, 0.11),
            zsa=(-0.3236, 0.0, 1.512, 0.0, 0.0, 0.16),
            k=(0.0, 0.0), xpr=(7.0, 3.0),
            sf=6.0, zsd_sigma=0.49, n_clusters=20, r_tau=2.3, zeta=3.0,
            c_ds=(0.25, 6.5622, 3.4084), c_asd=2.0, c_asa=15.0, c_zsa=7.0,
            c_phi=1.289, c_theta=1.178,
            corr_dist=(50.0, 1.0, 40.0, 50.0, 50.0, 50.0, 50.0),
            xcorr={("SF", "DS"): -0.4, ("SF", "ASD"): -0.6, ("SF", "ZSA"): -0.4, ("DS", "ASD"): 0.4, ("DS", "ASA"): 0.6, ("DS", "ZSD"): -0.5, ("ASD", "ASA"): 0.4, ("ASD", "ZSD"): 0.5, ("ASD", "ZSA"): -0.1}),
        2: dict(  # O2I
            ds=(0.0, 0.0, -6.62, 0.0, 0.0, 0.32),
            asd=(0.0, 0.0, 1.25, 0.0, 0.0, 0.42),
            asa=(0.0, 0.0, 1.76, 0.0, 0.0, 0.16),
            zsa=(0.0, 0.0, 1.01, 0.0, 0.0, 0.43),
            k=(0.0, 0.0), xpr=(9.0, 5.0),
            sf=7.0, zsd_sigma=0.49, n_clusters=12, r_tau=2.2, zeta=4.0,
            c_ds=(11.0, 0.0, 0.0), c_asd=5.0, c_asa=8.0, c_zsa=3.0,
            c_phi=1.146, c_theta=1.104,
            corr_dist=(7.0, 1.0, 10.0, 11.0, 17.0, 25.0, 25.0),
            xcorr={("SF", "DS"): -0.5, ("SF", "ASD"): 0.2, ("DS", "ASD"): 0.4, ("DS", "ASA"): 0.4, ("DS", "ZSD"): -0.6, ("DS", "ZSA"): -0.2, ("ASD", "ZSD"): -0.2, ("ASA", "ZSA"): 0.5, ("ZSD", "ZSA"): 0.5}),
    },
    "umi": {
        0: dict(  # LoS
            ds=(-0.24, 1.0, -7.14, 0.0, 0.0, 0.38),
            asd=(-0.05, 1.0, 1.21, 0.0, 0.0, 0.41),
            asa=(-0.08, 1.0, 1.73, 0.014, 1.0, 0.28),
            zsa=(-0.1, 1.0, 0.73, -0.04, 1.0, 0.34),
            k=(9.0, 5.0), xpr=(9.0, 3.0),
            sf=4.0, zsd_sigma=0.35, n_clusters=12, r_tau=3.0, zeta=3.0,
            c_ds=(5.0, 0.0, 0.0), c_asd=3.0, c_asa=17.0, c_zsa=7.0,
            c_phi=1.146, c_theta=1.104,
            corr_dist=(10.0, 15.0, 7.0, 8.0, 8.0, 12.0, 12.0),
            xcorr={("SF", "K"): 0.5, ("SF", "DS"): -0.4, ("SF", "ASD"): -0.5, ("SF", "ASA"): -0.4, ("K", "DS"): -0.7, ("K", "ASD"): -0.2, ("K", "ASA"): -0.3, ("DS", "ASD"): 0.5, ("DS", "ASA"): 0.8, ("DS", "ZSA"): 0.2, ("ASD", "ASA"): 0.4, ("ASD", "ZSD"): 0.5, ("ASD", "ZSA"): 0.3}),
        1: dict(  # NLoS
            ds=(-0.24, 1.0, -6.83, 0.16, 1.0, 0.28),
            asd=(-0.23, 1.0, 1.53, 0.11, 1.0, 0.33),
            asa=(-0.08, 1.0, 1.81, 0.05, 1.0, 0.3),
            zsa=(-0.04, 1.0, 0.92, -0.07, 1.0, 0.41),
            k=(0.0, 0.0), xpr=(8.0, 3.0),
            sf=7.82, zsd_sigma=0.35, n_clusters=19, r_tau=2.1, zeta=3.0,
            c_ds=(11.0, 0.0, 0.0), c_asd=10.0, c_asa=22.0, c_zsa=7.0,
            c_phi=1.273, c_theta=1.184,
            corr_dist=(13.0, 1.0, 10.0, 10.0, 9.0, 10.0, 10.0),
            xcorr={("SF", "DS"): -0.7, ("SF", "ASA"): -0.4, ("DS", "ASA"): 0.4, ("DS", "ZSD"): -0.5, ("ASD", "ZSD"): 0.5, ("ASD", "ZSA"): 0.5, ("ASA", "ZSA"): 0.2}),
        2: dict(  # O2I
            ds=(0.0, 0.0, -6.62, 0.0, 0.0, 0.32),
            asd=(0.0, 0.0, 1.25, 0.0, 0.0, 0.42),
            asa=(0.0, 0.0, 1.76, 0.0, 0.0, 0.16),
            zsa=(0.0, 0.0, 1.01, 0.0, 0.0, 0.43),
            k=(0.0, 0.0), xpr=(9.0, 5.0),
            sf=7.0, zsd_sigma=0.35, n_clusters=12, r_tau=2.2, zeta=4.0,
            c_ds=(11.0, 0.0, 0.0), c_asd=5.0, c_asa=8.0, c_zsa=3.0,
            c_phi=1.146, c_theta=1.104,
            corr_dist=(7.0, 1.0, 10.0, 11.0, 17.0, 25.0, 25.0),
            xcorr={("SF", "DS"): -0.5, ("SF", "ASD"): 0.2, ("DS", "ASD"): 0.4, ("DS", "ASA"): 0.4, ("DS", "ZSD"): -0.6, ("DS", "ZSA"): -0.2, ("ASD", "ZSD"): -0.2, ("ASA", "ZSA"): 0.5, ("ZSD", "ZSA"): 0.5}),
    },
    "rma": {
        0: dict(  # LoS
            ds=(0.0, 0.0, -7.49, 0.0, 0.0, 0.55),
            asd=(0.0, 0.0, 0.9, 0.0, 0.0, 0.38),
            asa=(0.0, 0.0, 1.52, 0.0, 0.0, 0.24),
            zsa=(0.0, 0.0, 0.47, 0.0, 0.0, 0.4),
            k=(7.0, 4.0), xpr=(12.0, 4.0),
            sf=8.0, zsd_sigma=0.34, n_clusters=11, r_tau=3.8, zeta=3.0,
            c_ds=(3.91, 0.0, 0.0), c_asd=2.0, c_asa=3.0, c_zsa=3.0,
            c_phi=1.123, c_theta=1.031,
            corr_dist=(37.0, 40.0, 50.0, 25.0, 35.0, 15.0, 15.0),
            xcorr={("SF", "DS"): -0.5, ("SF", "ZSD"): 0.01, ("SF", "ZSA"): -0.17, ("K", "ZSA"): -0.02, ("DS", "ZSD"): -0.05, ("DS", "ZSA"): 0.27, ("ASD", "ZSD"): 0.73, ("ASD", "ZSA"): -0.14, ("ASA", "ZSD"): -0.2, ("ASA", "ZSA"): 0.24, ("ZSD", "ZSA"): -0.07}),
        1: dict(  # NLoS
            ds=(0.0, 0.0, -7.43, 0.0, 0.0, 0.48),
            asd=(0.0, 0.0, 0.95, 0.0, 0.0, 0.45),
            asa=(0.0, 0.0, 1.52, 0.0, 0.0, 0.13),
            zsa=(0.0, 0.0, 0.58, 0.0, 0.0, 0.37),
            k=(0.0, 0.0), xpr=(7.0, 3.0),
            sf=8.0, zsd_sigma=0.3, n_clusters=10, r_tau=1.7, zeta=3.0,
            c_ds=(3.91, 0.0, 0.0), c_asd=2.0, c_asa=3.0, c_zsa=3.0,
            c_phi=1.09, c_theta=0.957,
            corr_dist=(120.0, 1.0, 36.0, 30.0, 40.0, 50.0, 50.0),
            xcorr={("SF", "DS"): -0.5, ("SF", "ASD"): 0.6, ("SF", "ZSD"): -0.04, ("SF", "ZSA"): -0.25, ("DS", "ASD"): -0.4, ("DS", "ZSD"): -0.1, ("DS", "ZSA"): -0.4, ("ASD", "ZSD"): 0.42, ("ASD", "ZSA"): -0.27, ("ASA", "ZSD"): -0.18, ("ASA", "ZSA"): 0.26, ("ZSD", "ZSA"): -0.27}),
        2: dict(  # O2I
            ds=(0.0, 0.0, -7.47, 0.0, 0.0, 0.24),
            asd=(0.0, 0.0, 0.67, 0.0, 0.0, 0.18),
            asa=(0.0, 0.0, 1.66, 0.0, 0.0, 0.21),
            zsa=(0.0, 0.0, 0.93, 0.0, 0.0, 0.22),
            k=(0.0, 0.0), xpr=(7.0, 3.0),
            sf=8.0, zsd_sigma=0.3, n_clusters=10, r_tau=1.7, zeta=3.0,
            c_ds=(3.91, 0.0, 0.0), c_asd=2.0, c_asa=3.0, c_zsa=3.0,
            c_phi=1.09, c_theta=0.957,
            corr_dist=(120.0, 1.0, 36.0, 30.0, 40.0, 50.0, 50.0),
            xcorr={("ASD", "ASA"): -0.7, ("ASD", "ZSD"): 0.66, ("ASD", "ZSA"): 0.47, ("ASA", "ZSD"): -0.55, ("ASA", "ZSA"): -0.22}),
    },
    "inh": {
        0: dict(  # LoS
            ds=(-0.01, 1.0, -7.692, 0.0, 0.0, 0.18),
            asd=(0.0, 0.0, 1.6, 0.0, 0.0, 0.18),
            asa=(-0.19, 1.0, 1.781, 0.12, 1.0, 0.119),
            zsa=(-0.26, 1.0, 1.44, -0.04, 1.0, 0.264),
            k=(7.0, 4.0), xpr=(11.0, 4.0),
            sf=3.0, zsd_sigma=0.0, n_clusters=15, r_tau=3.6, zeta=6.0,
            c_ds=(3.91, 0.0, 0.0), c_asd=5.0, c_asa=8.0, c_zsa=9.0,
            c_phi=1.211, c_theta=1.1088,
            corr_dist=(10.0, 4.0, 8.0, 7.0, 5.0, 4.0, 4.0),
            xcorr={("SF", "K"): 0.5, ("SF", "DS"): -0.8, ("SF", "ASD"): -0.4, ("SF", "ASA"): -0.5, ("SF", "ZSD"): 0.2, ("SF", "ZSA"): 0.3, ("K", "DS"): -0.5, ("K", "ZSA"): 0.1, ("DS", "ASD"): 0.6, ("DS", "ASA"): 0.8, ("DS", "ZSD"): 0.1, ("DS", "ZSA"): 0.2, ("ASD", "ASA"): 0.4, ("ASD", "ZSD"): 0.5, ("ASA", "ZSA"): 0.5}),
        1: dict(  # NLoS
            ds=(-0.28, 1.0, -7.173, 0.1, 1.0, 0.055),
            asd=(0.0, 0.0, 1.62, 0.0, 0.0, 0.25),
            asa=(-0.11, 1.0, 1.863, 0.12, 1.0, 0.059),
            zsa=(-0.15, 1.0, 1.387, -0.09, 1.0, 0.746),
            k=(0.0, 0.0), xpr=(10.0, 4.0),
            sf=8.03, zsd_sigma=0.0, n_clusters=19, r_tau=3.0, zeta=3.0,
            c_ds=(3.91, 0.0, 0.0), c_asd=5.0, c_asa=11.0, c_zsa=9.0,
            c_phi=1.273, c_theta=1.184,
            corr_dist=(6.0, 1.0, 5.0, 3.0, 3.0, 4.0, 4.0),
            xcorr={("SF", "DS"): -0.5, ("SF", "ASA"): -0.4, ("DS", "ASD"): 0.4, ("DS", "ZSD"): -0.27, ("DS", "ZSA"): -0.06, ("ASD", "ZSD"): 0.35, ("ASD", "ZSA"): 0.23, ("ASA", "ZSD"): -0.08, ("ASA", "ZSA"): 0.43, ("ZSD", "ZSA"): 0.42}),
    },
}


# ITU-R M.2412 channel model A, InH below 6 GHz (Table A1-16, first column
# pair): the TR 38.901 InH table with constant DS / ASA / ZSA statistics,
# SF of 3 / 4 dB and Laplacian azimuth spectra (eq. 13b / 14b, C_phi^NLOS =
# 1.434 for 15 clusters, 1.501 for 19).  ZSD in Table A1-17 (lsp.py).
import copy as _copy  # noqa: E402

PARAMS["inh_a"] = _copy.deepcopy(PARAMS["inh"])
PARAMS["inh_a"][0].update(ds=(0.0, 0.0, -7.70, 0.0, 0.0, 0.18),
                          asa=(0.0, 0.0, 1.62, 0.0, 0.0, 0.22),
                          zsa=(0.0, 0.0, 1.22, 0.0, 0.0, 0.23),
                          sf=3.0, zsd_sigma=0.41, c_phi=1.434, az_laplacian=True)
PARAMS["inh_a"][1].update(ds=(0.0, 0.0, -7.41, 0.0, 0.0, 0.14),
                          asa=(0.0, 0.0, 1.77, 0.0, 0.0, 0.16),
                          zsa=(0.0, 0.0, 1.26, 0.0, 0.0, 0.67),
                          sf=4.0, zsd_sigma=0.36, c_phi=1.501, az_laplacian=True)

