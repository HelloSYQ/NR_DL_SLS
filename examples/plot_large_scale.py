#!/usr/bin/env python3
"""Phase-1 figures: large-scale calibration CDFs, the default system, and a
layout map.

Writes
  results/p1_calibration_6ghz.png   UMa / UMi / InH, TR 38.901 7.8.1-style
  results/p1_system_uma35.png       UMa 3.5 GHz 32T4R, O2I model sensitivity
  results/p1_layout_uma35.png       sites, sectors, UTs coloured by geometry
  results/p1_summary.json           percentiles of every run
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.config.scenario import get_preset  # noqa: E402
from nrsls.engine.drop import generate_drop  # noqa: E402
from nrsls.engine.simulator import run_large_scale  # noqa: E402
from nrsls.metrics.kpi import large_scale_summary  # noqa: E402
from nrsls.plots import cdf  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
DROPS, SEED, JOBS = 50, 1, 4


def two_panel(runs: dict, title: str, path: str):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=cdf.SURFACE)
    cdf.plot_cdfs(ax[0], {k: v.coupling_gain_db for k, v in runs.items()},
                  "Coupling gain to the serving cell [dB]  (= -coupling loss)")
    cdf.plot_cdfs(ax[1], {k: v.geometry_db for k, v in runs.items()},
                  "Geometry (wideband SINR, no fast fading) [dB]")
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=cdf.INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    plt.close(fig)
    print("wrote", os.path.normpath(path))


def layout_map(path: str):
    cfg = get_preset("system", ue_per_cell=30)
    d = generate_drop(cfg, np.random.default_rng(3))
    lay = d.layout
    fig, ax = plt.subplots(figsize=(7.2, 6.4), facecolor=cdf.SURFACE)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "blue", cdf.SEQUENTIAL)
    sc = ax.scatter(d.ues.xy[:, 0], d.ues.xy[:, 1], c=d.geometry_db, s=9,
                    cmap=cmap, vmin=-5, vmax=25, linewidths=0)
    # wrap-around copies of the sites, then the real sites + boresights
    for t in lay.wrap_offsets[1:]:
        ax.plot(*(lay.site_xy + t).T, "o", ms=2.5, color=cdf.AXIS)
    ax.plot(*lay.site_xy.T, "o", ms=4.5, color=cdf.INK)
    r = 0.28 * lay.isd_m
    for c in range(lay.n_cells):
        o = lay.site_xy[lay.cell_site[c]]
        b = np.deg2rad(lay.cell_bearing_deg[c])
        ax.plot([o[0], o[0] + r * np.cos(b)], [o[1], o[1] + r * np.sin(b)],
                color=cdf.INK_2, lw=0.8)
    lim = 3.2 * lay.isd_m
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", fontsize=9)
    ax.set_ylabel("y [m]", fontsize=9)
    ax.set_title("UMa 19 sites x 3 sectors, 30 UTs per cell: UT geometry "
                 "(grey dots: wrap-around site copies)", fontsize=9, loc="left")
    cdf.style_axes(ax)
    cb = fig.colorbar(sc, ax=ax, shrink=0.8)
    cb.set_label("Geometry [dB]", color=cdf.INK_2, fontsize=9)
    cb.ax.tick_params(colors=cdf.MUTED, labelcolor=cdf.INK_2, labelsize=8)
    cb.outline.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    plt.close(fig)
    print("wrote", os.path.normpath(path))


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {}

    calib = {}
    for name, label in [("calib-uma", "UMa"), ("calib-umi", "UMi"),
                        ("calib-inh", "InH-open")]:
        calib[label] = run_large_scale(get_preset(name), DROPS, SEED, JOBS)
        summary[name] = large_scale_summary(calib[label])
    two_panel(calib, f"Large-scale calibration, 6 GHz, 20 MHz "
              f"(TR 38.901 Table 7.8-1 style), {DROPS} drops",
              os.path.join(OUT, "p1_calibration_6ghz.png"))

    system = {}
    for label, kw in [("O2I 80 % low / 20 % high loss (default)", {}),
                      ("O2I low loss only", {"o2i_model": "low"}),
                      ("O2I legacy (20 dB, Table 7.4.3-3)",
                       {"o2i_model": "legacy"})]:
        system[label] = run_large_scale(get_preset("system", **kw), DROPS,
                                        SEED, JOBS)
        summary[f"system | {label}"] = large_scale_summary(system[label])
    two_panel(system, f"UMa 3.5 GHz, 100 MHz, 32T4R: O2I model sensitivity, "
              f"{DROPS} drops", os.path.join(OUT, "p1_system_uma35.png"))

    layout_map(os.path.join(OUT, "p1_layout_uma35.png"))

    with open(os.path.join(OUT, "p1_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("wrote", os.path.normpath(os.path.join(OUT, "p1_summary.json")))


if __name__ == "__main__":
    main()
