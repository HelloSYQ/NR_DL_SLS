#!/usr/bin/env python3
"""Figure of the FTP model 3 codeword-mapping evaluation (rank <= 4): gain of
LTE-style and one-codeword-per-layer mappings over NR in mean, 5th- and
95th-percentile UPT, per precoding case, receiver and load.  Bars pool the
files of all drops; dots are the single drops (mean UPT).

    python examples/plot_cw2lm_ftp.py [results/cw2lm_ftp.json] [out.png]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import matplotlib                                                     # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                       # noqa: E402
import numpy as np                                                    # noqa: E402

from nrsls.plots.cdf import AXIS, INK, INK_2, MUTED, SERIES, SURFACE, style_axes  # noqa: E402
from plot_cw2lm_rank4 import _bar                                     # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
VARIANTS = (("irc-olla", "MMSE-IRC"), ("sic-olla", "CW-level SIC"))
SCHEMES = (("lte", "LTE style (Alt2)"), ("per_layer", "1 CW per layer (Alt3)"))
CASES = (("etype2_20ms", "eType-II codebook, CSI every 20 ms, 4 ms old"),
         ("svd_sb_20ms", "Reciprocity (sub-band SVD), every 20 ms, 4 ms old"))
LOADS = ("20", "50", "70")
METRICS = (("upt_mean", "Mean UPT gain over NR"), ("upt_p5", "5th-pct UPT gain over NR"),
           ("upt_p95", "95th-pct UPT gain over NR"))
BAR_W = 0.36


def _panel_values(conf: dict, case: str, metric: str) -> list:
    """[(x, pooled gain, per-drop gains, colour)]; x groups are
    (receiver, load), receivers side by side."""
    gap = 0.03
    vals = []
    for i, (variant, _) in enumerate(VARIANTS):
        for k, load in enumerate(LOADS):
            e = conf.get((case, load)) or {}
            for j, (scheme, _) in enumerate(SCHEMES):
                g = e.get("variants", {}).get(variant, {}).get(scheme, {}).get("gain_vs_nr_pct")
                v = g[metric] if g else np.nan
                per = g["upt_mean_per_drop"] if (g and metric == "upt_mean") else []
                x = i * (len(LOADS) + 0.6) + k + (j - 0.5) * (BAR_W + gap)
                vals.append((x, v, per, SERIES[j]))
    return vals


def plot(summ: dict, path: str) -> None:
    conf = {(e["case"], e["load"]): e for e in summ["configurations"]}
    centres = [i * (len(LOADS) + 0.6) + k for i in range(len(VARIANTS))
               for k in range(len(LOADS))]
    fig, axes = plt.subplots(len(METRICS), len(CASES), figsize=(11.0, 9.4),
                             facecolor=SURFACE, sharey="row", squeeze=False)
    for row, (metric, metric_label) in enumerate(METRICS):
        panels = [_panel_values(conf, case, metric) for case, _ in CASES]
        finite = [x for vals in panels for _, v, per, _ in vals for x in [v, *per]
                  if np.isfinite(x)]
        span = max([max(finite, default=0) - min(finite + [0], default=0), 2.0])
        lim = max(finite + [1.0]) + 0.2 * span
        lo = min(finite + [0.0]) - (0.2 * span if min(finite + [0.0]) < 0 else 0.0)
        for col in range(len(CASES)):
            ax = axes[row, col]
            style_axes(ax)
            ax.grid(False, axis="x")
            ax.set_ylim(lo, lim)
            ax.set_xlim(centres[0] - 0.6, centres[-1] + 0.6)
        fig.tight_layout(rect=(0, 0.03, 1, 0.93))
        fig.canvas.draw()                          # fix the transforms for _bar
        for col, (case, case_label) in enumerate(CASES):
            ax = axes[row, col]
            off = 0.03 * (lim - lo)
            for x, v, per, color in panels[col]:
                _bar(ax, x, BAR_W, v, color)
                if np.isfinite(v):
                    end = max([v, *per]) if v >= 0 else min([v, *per])   # clear the dots
                    ax.text(x, end + (off if v >= 0 else -off),
                            f"{v:+.0f}" if round(v) else "0",
                            ha="center", va="bottom" if v >= 0 else "top",
                            fontsize=6.5, color=INK_2)
                for p in per:
                    ax.plot([x], [p], "o", ms=3.0, mfc=INK, mec=SURFACE, mew=0.8, zorder=3)
            ax.axhline(0, color=AXIS, lw=0.9, zorder=1)
            ax.axvline((centres[len(LOADS) - 1] + centres[len(LOADS)]) / 2, color=AXIS,
                       lw=0.6, ls=(0, (2, 3)), zorder=1)
            ax.set_xticks(centres)
            ax.set_xticklabels([f"{ld} % RU" for _ in VARIANTS for ld in LOADS], fontsize=7.5)
            for i, (_, vlabel) in enumerate(VARIANTS):
                ax.text(np.mean(centres[i * len(LOADS):(i + 1) * len(LOADS)]), 0.97, vlabel,
                        transform=ax.get_xaxis_transform(), ha="center", va="top",
                        fontsize=8, color=INK_2)
            ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6, steps=[1, 2, 5, 10]))
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
                lambda y, _: f"{y:+g} %" if abs(y) > 1e-9 else "0"))
            if col == 0:
                ax.set_ylabel(metric_label, fontsize=9)
            if row == 0:
                ax.set_title(case_label, fontsize=9.5, loc="left", color=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for c in SERIES[:len(SCHEMES)]]
    handles.append(plt.Line2D([], [], ls="", marker="o", ms=3.0, mfc=INK, mec=SURFACE))
    leg = fig.legend(handles, [lab for _, lab in SCHEMES] + ["single drop (mean UPT)"],
                     loc="upper left", bbox_to_anchor=(0.005, 0.968), ncol=3,
                     frameon=False, fontsize=8)
    for t in leg.get_texts():
        t.set_color(INK_2)
    fig.suptitle("Codeword-to-layer mapping up to rank 4, FTP model 3, Dense Urban A: "
                 "UPT gain over NR", x=0.01, y=0.99, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.008, "NR (one codeword, MMSE-IRC) = 0, with the same files. Loads are "
             "set by NR's resource utilisation; OLLA per codeword for every scheme.",
             fontsize=7.5, color=MUTED)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "cw2lm_ftp.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT, "cw2lm_ftp.png")
    with open(src) as fh:
        plot(json.load(fh), out)
    print("wrote", os.path.normpath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
