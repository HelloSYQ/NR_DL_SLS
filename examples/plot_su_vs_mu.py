#!/usr/bin/env python3
"""SU- vs MU-MIMO UT spectral-efficiency CDFs, one panel per CSI report type.

Reads the per-UT SE samples written by ``run_full_buffer.py`` for the SU run
(``--tag p3``) and the MU run (``--mu --max-rank 2 --tag p4_mu``) and writes
results/p4_su_vs_mu_cdf.png.

    python examples/plot_su_vs_mu.py [--su results/p3_full_buffer.json]
                                     [--mu results/p4_mu_full_buffer.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
LABELS = {"type1": "Type-I", "etype2": "eType-II (combination 6)",
          "svd": "SVD (ideal CSI)", "svd_sb": "Sub-band SVD (ideal CSI)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--su", default=os.path.join(OUT, "p3_full_buffer.json"))
    ap.add_argument("--mu", default=os.path.join(OUT, "p4_mu_full_buffer.json"))
    ap.add_argument("--out", default=os.path.join(OUT, "p4_su_vs_mu_cdf.png"))
    args = ap.parse_args()
    su, mu = json.load(open(args.su)), json.load(open(args.mu))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.metrics.kpi import ecdf
    from nrsls.plots import cdf

    kinds = [k for k in LABELS if k in su["ue_se"] and k in mu["ue_se"]]
    fig, axes = plt.subplots(1, len(kinds), figsize=(3.3 * len(kinds), 3.6),
                             facecolor=cdf.SURFACE, sharey=True)
    xmax = max(max(su["ue_se"][k] + mu["ue_se"][k]) for k in kinds)
    for ax, k in zip(axes, kinds):
        for color, (name, run) in zip(cdf.SERIES, [("SU-MIMO", su), ("MU-MIMO", mu)]):
            x, f = ecdf(run["ue_se"][k])
            r = run["results"][k]
            ax.plot(x, f, color=color, lw=cdf.LINE_PT, solid_capstyle="round",
                    label=f"{name}: cell {r['cell_se']:.2f}, 5 % {r['ue_se_p5']:.3f}")
        ax.set_xlim(0, min(xmax, 3.0))
        ax.set_ylim(0, 1)
        ax.set_xlabel("UT SE [bit/s/Hz]", fontsize=9)
        ax.set_title(LABELS[k], fontsize=9.5, loc="left")
        cdf.style_axes(ax)
        leg = ax.legend(fontsize=7, frameon=False, loc="lower right")
        for t in leg.get_texts():
            t.set_color(cdf.INK_2)
    axes[0].set_ylabel("CDF", fontsize=9)
    fig.suptitle(f"{mu['config']['preset']}: full buffer, "
                 f"{mu['config']['ue_per_cell']} UTs/cell, SU (RI ≤ {su['config'].get('max_rank', 4)}) "
                 f"vs MU (RI ≤ {mu['config']['max_rank']}, ≤ {mu['config']['mu_max_ues']} UTs / "
                 f"{mu['config']['mu_max_layers']} layers per RBG)",
                 fontsize=9.5, x=0.01, ha="left", color=cdf.INK)
    fig.tight_layout()
    path = args.out
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
