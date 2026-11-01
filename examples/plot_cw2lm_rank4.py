#!/usr/bin/env python3
"""Figure of the rank <= 4 codeword-mapping evaluation: gain of LTE-style
and one-codeword-per-layer mappings over NR, per CSI case, receiver and link
adaptation.  Bars are the gain over the drops pooled, dots the single drops.

    python examples/plot_cw2lm_rank4.py [results/cw2lm_rank4.json] [out.png]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib                                                     # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                       # noqa: E402
import numpy as np                                                    # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle              # noqa: E402

from nrsls.plots.cdf import (AXIS, INK, INK_2, MUTED, SERIES, SURFACE,  # noqa: E402
                             style_axes)

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
VARIANTS = (("irc-olla", "MMSE-IRC\nOLLA"), ("irc-ideal", "MMSE-IRC\nideal LA"),
            ("sic-olla", "SIC\nOLLA"), ("sic-ideal", "SIC\nideal LA"))
SCHEMES = (("lte", "LTE style"), ("per_layer", "1 CW per layer"))
CASES = (("etype2_20ms", "eType-II, CSI every 20 ms, 4 ms old"),
         ("svd_2ms", "Wideband SVD, CSI every 2 ms, fresh"))
BAR_W = 0.34
METRICS = (("cell_se", "Cell SE gain over NR"), ("ue_se_p5", "5th-pct UT SE gain over NR"))


def _bar(ax, x, width, value, color, radius_px=3.0):
    """Vertical bar from 0 to ``value`` with a rounded data end and a square
    baseline end: a rounded box extended past the baseline, clipped at it."""
    if value == 0 or not np.isfinite(value):
        return
    # data units per pixel, to keep the corner circular
    (x0, y0), (x1, y1) = ax.transData.inverted().transform([(0, 0), (1, 1)])
    rx, ry = radius_px * abs(x1 - x0), radius_px * abs(y1 - y0)
    r = min(rx, width / 2)
    ext = ry * 2
    lo, hi = (min(0, value), max(0, value))
    box = FancyBboxPatch((x - width / 2, lo - (ext if value > 0 else 0)), width,
                         hi - lo + ext, boxstyle=f"round,pad=0,rounding_size={r}",
                         mutation_aspect=ry / rx, facecolor=color, edgecolor="none",
                         zorder=2)
    ax.add_patch(box)
    box.set_clip_path(Rectangle((x - width, lo), 2 * width, hi - lo,
                                transform=ax.transData))


def _configs(summ: dict) -> dict:
    """{(case, variant): entry} keeping the longest run of each."""
    out = {}
    for e in summ["configurations"]:
        k = (e["case"], e["variant"])
        if k not in out or e["n_slots"] > out[k]["n_slots"]:
            out[k] = e
    return out


def _panel_values(cfgs: dict, case: str, metric: str) -> list:
    """[(x, pooled gain, per-drop gains, colour)] of one panel."""
    width, gap = BAR_W, 0.03
    vals = []
    for i, (variant, _) in enumerate(VARIANTS):
        e = cfgs.get((case, variant)) or {}
        for j, (scheme, _) in enumerate(SCHEMES):
            g = e.get("schemes", {}).get(scheme, {}).get("gain_vs_nr_pct")
            v = g[metric] if g else np.nan
            per = g["cell_se_per_drop"] if (g and metric == "cell_se") else []
            vals.append((i + (j - 0.5) * (width + gap), v, per, SERIES[j]))
    return vals


def plot(summ: dict, log: list | None, path: str) -> None:
    cfgs = _configs(summ)
    fig, axes = plt.subplots(len(METRICS), len(CASES), figsize=(9.6, 6.4),
                             facecolor=SURFACE, sharey="row", squeeze=False)
    for row, (metric, metric_label) in enumerate(METRICS):
        panels = [_panel_values(cfgs, case, metric) for case, _ in CASES]
        finite = [x for vals in panels for _, v, per, _ in vals for x in [v, *per]
                  if np.isfinite(x)]
        span = max([max(finite, default=0) - min(finite + [0], default=0), 2.0])
        lim = max(finite + [1.0]) + 0.18 * span
        lo = min(finite + [0.0]) - (0.18 * span if min(finite + [0.0]) < 0 else 0.0)
        for col, (case, case_label) in enumerate(CASES):
            ax = axes[row, col]
            style_axes(ax)
            ax.grid(False, axis="x")
            ax.set_ylim(lo, lim)
            ax.set_xlim(-0.6, len(VARIANTS) - 0.4)
        fig.tight_layout(rect=(0, 0.02, 1, 0.95))
        fig.canvas.draw()                          # fix the transforms for _bar
        for col, (case, case_label) in enumerate(CASES):
            ax = axes[row, col]
            off = 0.03 * (lim - lo)
            for x, v, per, color in panels[col]:
                _bar(ax, x, BAR_W, v, color)
                if np.isfinite(v):
                    end = max([v, *per]) if v >= 0 else min([v, *per])   # clear the dots
                    ax.text(x, end + (off if v >= 0 else -off), f"{v:+.1f}",
                            ha="center", va="bottom" if v >= 0 else "top",
                            fontsize=7, color=INK_2)
                for p in per:
                    ax.plot([x], [p], "o", ms=3.6, mfc=INK, mec=SURFACE, mew=1.0, zorder=3)
            ax.axhline(0, color=AXIS, lw=0.9, zorder=1)
            ax.set_xticks(range(len(VARIANTS)))
            ax.set_xticklabels([lab for _, lab in VARIANTS], fontsize=8)
            ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6, steps=[1, 2, 5, 10]))
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
                lambda y, _: f"{y:+g} %" if abs(y) > 1e-9 else "0"))
            if col == 0:
                ax.set_ylabel(metric_label, fontsize=9)
            if row == 0:
                ax.set_title(case_label, fontsize=10, loc="left", color=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for c in SERIES[:len(SCHEMES)]]
    handles.append(plt.Line2D([], [], ls="", marker="o", ms=3.6, mfc=INK, mec=SURFACE))
    leg = fig.legend(handles, [lab for _, lab in SCHEMES] + ["single drop (cell SE)"],
                     loc="upper right", ncol=3, frameon=False, fontsize=8)
    for t in leg.get_texts():
        t.set_color(INK_2)
    fig.suptitle("Codeword-to-layer mapping up to rank 4, Dense Urban A: gain over NR",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "NR (one codeword) = 0. The SIC variants are compared with NR "
             "under the same link adaptation; with one codeword SIC is MMSE-IRC.",
             fontsize=7.5, color=MUTED)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "cw2lm_rank4.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT, "cw2lm_rank4.png")
    with open(src) as fh:
        plot(json.load(fh), None, out)
    print("wrote", os.path.normpath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
