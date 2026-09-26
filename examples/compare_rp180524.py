#!/usr/bin/env python3
"""Compare nrsls against the RP-180524 per-company calibration data.

For every RP-180524 configuration that nrsls can set up (channel model A),
run large-scale drops and report the gap to the company mean at the
5/10/20/50/80/90/95th percentiles, and how many of those percentiles fall
inside the companies' min-max envelope.  Needs refs/rp180524 (run
examples/import_rp180524.py first).

Phase 1 computes the BS gain toward the LOS direction; the calibration uses
the multi-path RSRP of TR 36.873 eq. (8.1-1), so this comparison is
indicative until phase 2.

    python examples/compare_rp180524.py [--drops 30] [--jobs 4]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.config.scenario import get_preset  # noqa: E402
from nrsls.engine.simulator import run_large_scale  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "refs", "rp180524")
OUT = os.path.join(HERE, "..", "results")
PCT = np.array([5, 10, 20, 50, 80, 90, 95])
SHEETS = {
    "rp-rural-700m": "Rural_700M_ModelA",
    "rp-rural-4g": "Rural_4GHz_ModelA",
    "rp-rural-lmlc": "Rural_LMLC_ModelA",
    "rp-mmtc-500m": "UMa_mMTC_500m_ModelA",
    "rp-mmtc-1732m": "UMa_mMTC_1732m_ModelA",
    "rp-urllc-4g": "UMa_URLLC_4GHz_ModelA",
    "rp-urllc-700m": "UMa_URLLC_700MHz_ModelA",
}


def load_ref(sheet, metric):
    d = np.genfromtxt(os.path.join(REFS, f"{sheet}_{metric}.csv"),
                      delimiter=",", names=True, skip_header=1)
    return d


def compare(samples, ref):
    s = np.percentile(samples, PCT)
    m, lo, hi = ref["mean"][PCT], ref["min"][PCT], ref["max"][PCT]
    return {"gap_db": dict(zip((f"p{p}" for p in PCT), np.round(s - m, 2).tolist())),
            "in_envelope": float(np.mean((s >= lo) & (s <= hi)))}


def figure(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.plots import cdf
    show = ["rp-rural-700m", "rp-urllc-4g"]
    fig, axs = plt.subplots(2, 2, figsize=(11, 8), facecolor=cdf.SURFACE)
    for row, name in enumerate(show):
        st = results[name]
        for col, metric in enumerate(("coupling_gain", "geometry")):
            ax = axs[row, col]
            ref = load_ref(SHEETS[name], metric)
            f = ref["pct"] / 100
            ax.fill_betweenx(f, ref["min"], ref["max"], color=cdf.SERIES[0],
                             alpha=0.12, lw=0, label="companies (min-max)")
            ax.plot(ref["mean"], f, color=cdf.SERIES[0], lw=cdf.LINE_PT,
                    label="company mean")
            x = np.sort(st[metric])
            ax.plot(x, np.arange(1, len(x) + 1) / len(x), color=cdf.SERIES[1],
                    lw=cdf.LINE_PT, label="nrsls phase 1 (LOS-direction gain)")
            ax.set_ylim(0, 1)
            ax.set_xlabel(("Coupling gain" if col == 0 else "Geometry")
                          + " [dB]", fontsize=9)
            ax.set_ylabel("CDF", fontsize=9)
            ax.set_title(f"{SHEETS[name]}", fontsize=10, loc="left")
            cdf.style_axes(ax)
            leg = ax.legend(fontsize=8, frameon=False, loc="lower right")
            for t in leg.get_texts():
                t.set_color(cdf.INK_2)
    fig.suptitle("RP-180524 calibration data vs nrsls phase 1 (indicative)",
                 x=0.01, ha="left", fontsize=11, color=cdf.INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    print("wrote", os.path.normpath(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drops", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    summary, samples = {}, {}
    for name, sheet in SHEETS.items():
        st = run_large_scale(get_preset(name), args.drops, args.seed, args.jobs)
        samples[name] = {"coupling_gain": st.coupling_gain_db,
                         "geometry": st.geometry_db}
        summary[name] = {"sheet": sheet}
        for metric in ("coupling_gain", "geometry"):
            summary[name][metric] = compare(samples[name][metric],
                                            load_ref(sheet, metric))
        c, g = summary[name]["coupling_gain"], summary[name]["geometry"]
        print(f"{name:15s} coupling gap " + " ".join(
            f"{v:+5.1f}" for v in c["gap_db"].values())
            + f" (in env {c['in_envelope']:.0%})   geometry gap " + " ".join(
            f"{v:+5.1f}" for v in g["gap_db"].values())
            + f" (in env {g['in_envelope']:.0%})")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "p1_rp180524_gaps.json"), "w") as f:
        json.dump(summary, f, indent=1)
    figure(samples, os.path.join(OUT, "p1_rp180524.png"))


if __name__ == "__main__":
    main()
