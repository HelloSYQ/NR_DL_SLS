#!/usr/bin/env python3
"""Figure of the FTP screen (docs/cw2lm-ftp-screen.md): UPT gain of one
codeword per layer over NR in mean, 5th and 95th percentile, per precoder and
load, for the HARQ fix and the rank-adaptation options A and B, against the
target (mean and p95 >= +5 %, p5 >= 0 %).

    python examples/cw2lm_ftp_screen.py                    # writes the summary
    python examples/plot_cw2lm_ftp_screen.py [results/cw2lm_ftp_screen_20mhz.json] [out.png]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib                                                     # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                       # noqa: E402

from nrsls.plots.cdf import (AXIS, GRID, INK, INK_2, LINE_PT, MUTED, SERIES,  # noqa: E402
                             SURFACE, style_axes)

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
CASES = (("etype2_20ms", "eType-II codebook, CSI every 20 ms, 4 ms old"),
         ("svd_sb_20ms", "Reciprocity (sub-band SVD), every 20 ms, 4 ms old"))
LOADS = ("20", "50", "70")
METRICS = (("upt_mean", "Mean UPT"), ("upt_p5", "5th-percentile UPT"),
           ("upt_p95", "95th-percentile UPT"))
TARGET = {"upt_mean": 5.0, "upt_p5": 0.0, "upt_p95": 5.0}
DODGE = 0.05
# (variant, label, colour, marker, line style); the coloured series in the
# fixed categorical order, the context series in ink tones.  fix + A + B
# tracks fix + B and is left to the table (a fourth hue would sit too close
# to the third)
SERIES_SPEC = (
    ("sic-olla", "SIC, before the fix", MUTED, "o", (0, (4, 2))),
    ("irc-fix", "MMSE-IRC + fix", INK_2, "s", (0, (1, 1.6))),
    ("sic-fix", "SIC + fix", SERIES[0], "o", "-"),
    ("sic-fix-a", "SIC + fix + A", SERIES[1], "D", "-"),
    ("sic-fix-b", "SIC + fix + B", SERIES[2], "^", "-"),
)


def _points(res: dict, case: str, variant: str, metric: str):
    out = []
    for i, load in enumerate(LOADS):
        cell = next((c for c in res["cells"] if c["case"] == case and c["load"] == load), None)
        row = cell and cell["rows"].get(variant)
        if row:
            out.append((i, row["vs_best_nr_pct"][metric], row["complete"]))
    return out


def figure(res: dict, path: str) -> None:
    fig, axs = plt.subplots(3, 2, figsize=(10.5, 9.6), facecolor=SURFACE, sharex=True,
                            sharey="row")
    for r, (metric, mlabel) in enumerate(METRICS):
        lo = min(min((p[1] for v, *_ in SERIES_SPEC for c, _ in CASES
                      for p in _points(res, c, v, metric)), default=0), TARGET[metric]) - 2
        hi = max(max((p[1] for v, *_ in SERIES_SPEC for c, _ in CASES
                      for p in _points(res, c, v, metric)), default=0), TARGET[metric]) + 2
        for col, (case, clabel) in enumerate(CASES):
            ax = axs[r, col]
            style_axes(ax)
            ax.grid(False, axis="x")
            t = TARGET[metric]
            ax.axhspan(lo, t, color=GRID, alpha=0.35, lw=0, zorder=0)
            ax.axhline(0, color=AXIS, lw=0.8, zorder=1)
            ax.axhline(t, color=INK_2, lw=0.9, ls=(0, (5, 3)), zorder=1)
            ax.text(2.32, t, f" target {t:+.0f} %".replace("+0", "0"), va="center",
                    ha="left", fontsize=7.5, color=INK_2, clip_on=False)
            for k, (variant, label, color, marker, ls) in enumerate(SERIES_SPEC):
                pts = _points(res, case, variant, metric)
                if not pts:
                    continue
                # a small horizontal dodge keeps coinciding markers apart
                dx = DODGE * (k - (len(SERIES_SPEC) - 1) / 2)
                pts = [(xi + dx, yi, ok) for xi, yi, ok in pts]
                x, y, done = zip(*pts)
                ax.plot(x, y, color=color, lw=LINE_PT, ls=ls, solid_capstyle="round",
                        zorder=2)
                for xi, yi, ok in pts:
                    ax.plot([xi], [yi], marker=marker, ms=6.5, ls="",
                            mfc=color if ok else SURFACE, mec=SURFACE if ok else color,
                            mew=1.2 if ok else 1.4, zorder=3)
            ax.set_ylim(lo, hi)
            ax.set_xlim(-0.25, 2.25)
            ax.set_xticks(range(len(LOADS)))
            ax.set_xticklabels([f"{x} %" for x in LOADS])
            if r == 0:
                ax.set_title(clabel, fontsize=9.5, loc="left", color=INK)
            if col == 0:
                ax.set_ylabel(f"{mlabel} gain over NR [%]", fontsize=8.5, color=INK_2)
            if r == len(METRICS) - 1:
                ax.set_xlabel("Load: NR's resource utilisation", fontsize=8.5, color=INK_2)
    handles = [plt.Line2D([], [], color=c, lw=LINE_PT, ls=ls, marker=m, ms=6.5, mfc=c,
                          mec=SURFACE, mew=1.2) for _, _, c, m, ls in SERIES_SPEC]
    leg = fig.legend(handles, [s[1] for s in SERIES_SPEC], loc="upper left",
                     bbox_to_anchor=(0.01, 0.955), ncol=5, frameon=False, fontsize=8.5,
                     handlelength=2.6, columnspacing=1.4)
    for txt in leg.get_texts():
        txt.set_color(INK_2)
    d = res["drops"]
    fig.suptitle("One codeword per layer (Alt 3) vs NR: FTP model 3, Dense Urban 4 GHz, "
                 f"20 MHz / 44 dBm, drops {d[0]}-{d[-1]}", x=0.01, y=0.995, ha="left",
                 fontsize=11, color=INK)
    fig.text(0.01, 0.008,
             "Gain over the better of NR and NR with B for each KPI (each scheme at its best). "
             "Shaded: below the target. Hollow: some drops not in yet.\n"
             "fix = refill decoded codewords only with fresh CSI and data;  A = SIC rank "
             "selection weights codeword k by 0.9^k;  B = per-rank OLLA and an OLLA-corrected "
             "rank selection.", fontsize=7.5, color=MUTED, va="bottom")
    fig.tight_layout(rect=(0, 0.045, 0.955, 0.94), h_pad=1.2, w_pad=1.6)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "cw2lm_ftp_screen_20mhz.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".png"
    with open(src) as fh:
        figure(json.load(fh), out)
    print("wrote", os.path.normpath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
