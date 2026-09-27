#!/usr/bin/env python3
"""LLS <-> SLS single-link regression sweep (module plan section 5).

Both simulators run on the same ``nrdlsim`` CDL channel realisations:

  1. SE vs SNR for the system array (32T4R, (N1, N2) = (8, 2)), CDL-C
     300 ns, 3 km/h, 52 RB at 30 kHz: the LLS, the SLS link in the matched
     set-up (per-RB SVD, wideband CQI) and the SLS link with its CSI options
     (wideband SVD, Rel-16 eType-II, Type-I with sub-band i2; 4-RB sub-bands);
  2. a matched-only matrix over channel models and array sizes.

Writes results/p3_lls_regression.json and results/p3_lls_regression.png.

    python examples/lls_regression.py [--jobs 4] [--seeds 3] [--slots 200]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.validation.lls import lls_config, matched_fb, sweep  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
SE_TOL = 0.04

MATRIX = [   # (label, lls_config kwargs)
    ("CDL-A 100 ns, 32T4R", dict(n1=8, n2=2, model="CDL-A", delay_spread_ns=100.0)),
    ("CDL-C 300 ns, 32T4R", dict(n1=8, n2=2, model="CDL-C", delay_spread_ns=300.0)),
    ("CDL-D 30 ns (LOS), 32T4R", dict(n1=8, n2=2, model="CDL-D", delay_spread_ns=30.0)),
    ("CDL-C 300 ns, 8T4R", dict(n1=4, n2=1, model="CDL-C", delay_spread_ns=300.0)),
    ("CDL-C 300 ns, 4T2R", dict(n1=2, n2=1, n_rx=2, model="CDL-C",
                                delay_spread_ns=300.0)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--slots", type=int, default=200)
    ap.add_argument("--n-rb", type=int, default=52)
    args = ap.parse_args()

    # 1. SE vs SNR, system array
    t0 = time.time()
    cfg = lls_config(n1=8, n2=2, n_rx=4, n_rb=args.n_rb, model="CDL-C",
                     delay_spread_ns=300.0, n_slots=args.slots)
    snrs = np.arange(-5.0, 30.1, 2.5)
    variants = {
        "lls": None,
        "sls_matched": matched_fb(cfg),
        "sls_svd": matched_fb(cfg, codebook="svd", rbg_size=4),
        "sls_etype2": matched_fb(cfg, codebook="etype2", rbg_size=4),
        "sls_type1": matched_fb(cfg, codebook="type1", rbg_size=4),
    }
    curves = sweep(cfg, snrs, variants, args.seeds, args.jobs)
    err = [s["se"] / l["se"] - 1 for l, s in zip(curves["lls"], curves["sls_matched"])]
    print(f"sweep ({time.time() - t0:.0f} s)")
    print(" SNR   LLS   matched  err%   SVD-wb  eType-II  Type-I")
    for i, s in enumerate(snrs):
        print(f"{s:5.1f} {curves['lls'][i]['se']:6.2f} {curves['sls_matched'][i]['se']:7.2f} "
              f"{100 * err[i]:+5.1f}  {curves['sls_svd'][i]['se']:6.2f}  "
              f"{curves['sls_etype2'][i]['se']:7.2f}  {curves['sls_type1'][i]['se']:6.2f}",
              flush=True)

    # 2. matched-only matrix
    t0 = time.time()
    matrix = []
    for label, kw in MATRIX:
        c = lls_config(n_rb=args.n_rb, n_slots=args.slots, **kw)
        r = sweep(c, [0.0, 10.0, 20.0], {"lls": None, "sls": matched_fb(c)},
                  args.seeds, args.jobs)
        for l, s in zip(r["lls"], r["sls"]):
            matrix.append(dict(config=label, snr_db=l["snr_db"], lls_se=l["se"],
                               sls_se=s["se"], se_err=s["se"] / l["se"] - 1,
                               lls_bler=l["bler"], sls_bler=s["bler"],
                               lls_rank=l["rank"], sls_rank=s["rank"]))
            print(f"{label:26s} {l['snr_db']:5.1f} dB  LLS {l['se']:6.2f}  "
                  f"SLS {s['se']:6.2f}  ({100 * matrix[-1]['se_err']:+.1f} %)  "
                  f"BLER {l['bler']:.3f}/{s['bler']:.3f}  "
                  f"rank {l['rank']:.2f}/{s['rank']:.2f}", flush=True)
    print(f"matrix ({time.time() - t0:.0f} s)")
    worst = max(abs(m["se_err"]) for m in matrix + [dict(se_err=e) for e in err])
    print(f"worst matched SE error {100 * worst:.1f} % (tolerance {100 * SE_TOL:.0f} %)")

    os.makedirs(OUT, exist_ok=True)
    meta = dict(model="CDL-C", delay_spread_ns=300.0, speed_kmh=3.0, n_rb=args.n_rb,
                scs_khz=30, ports="32T4R (N1, N2) = (8, 2)", slots=args.slots,
                seeds=args.seeds, subband_rb=4, etype2_combo=6)
    with open(os.path.join(OUT, "p3_lls_regression.json"), "w") as f:
        json.dump({"config": meta, "curves": curves, "matched_error": err,
                   "matrix": matrix, "tolerance": SE_TOL}, f, indent=1)

    plot(snrs, curves, err, args)


def plot(snrs, curves, err, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.plots import cdf

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(6.5, 6.2), facecolor=cdf.SURFACE,
                                  sharex=True, gridspec_kw=dict(height_ratios=[3, 1.3]))
    se = {k: [p["se"] for p in v] for k, v in curves.items()}
    series = [("sls_matched", "SLS link, matched (per-RB SVD)"),
              ("sls_svd", "SLS link, wideband SVD"),
              ("sls_etype2", "SLS link, eType-II (combination 6)"),
              ("sls_type1", "SLS link, Type-I (sub-band i2)")]
    for color, (k, label) in zip(cdf.SERIES, series):
        ax.plot(snrs, se[k], color=color, lw=cdf.LINE_PT, solid_capstyle="round",
                solid_joinstyle="round", label=label, zorder=2)
    ax.plot(snrs, se["lls"], ls="none", marker="o", ms=5.5, mfc=cdf.SURFACE,
            mec=cdf.INK, mew=1.1, label="LLS (nrdlsim run_point)", zorder=3)
    ax.set_ylabel("Spectral efficiency [bit/s/Hz]", fontsize=9)
    ax.set_ylim(bottom=0)
    ax.set_title(f"LLS vs SLS link: CDL-C 300 ns, 32T4R, {args.n_rb} RB, 3 km/h",
                 fontsize=10, loc="left")
    cdf.style_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    order = [4, 0, 1, 2, 3]
    leg = ax.legend([handles[i] for i in order], [labels[i] for i in order],
                    fontsize=8, frameon=False, loc="upper left")
    for t in leg.get_texts():
        t.set_color(cdf.INK_2)

    ax2.axhspan(-100 * SE_TOL, 100 * SE_TOL, color=cdf.GRID, alpha=0.6, lw=0,
                zorder=0)
    ax2.axhline(0, color=cdf.AXIS, lw=0.8, zorder=1)
    ax2.plot(snrs, 100 * np.array(err), color=cdf.SERIES[0], lw=cdf.LINE_PT,
             marker="o", ms=4.5, mec=cdf.SURFACE, mew=1.0, zorder=2)
    ax2.set_ylim(-3 * 100 * SE_TOL / 2, 3 * 100 * SE_TOL / 2)
    ax2.set_xlabel("SNR [dB]", fontsize=9)
    ax2.set_ylabel("Matched SLS − LLS\nSE [%]", fontsize=9)
    ax2.text(snrs[0], 100 * SE_TOL * 0.93, f"±{100 * SE_TOL:.0f} % test tolerance",
             fontsize=7.5, color=cdf.MUTED, va="top")
    cdf.style_axes(ax2)
    fig.tight_layout()
    path = os.path.join(OUT, "p3_lls_regression.png")
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
