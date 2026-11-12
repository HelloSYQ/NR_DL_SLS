#!/usr/bin/env python3
"""Data and figure of the final CW2L report: FTP model 1, 20 MHz, MMSE-IRC,
fair baseline (variant irc-fix-warmfast-pr-rtt4), with the hand grip
(set-up 20mhz-ftp1-grip-hand-fair) and, as the reference, without it
(set-up 20mhz-ftp1, results/cw2lm_ftp1_fair_20mhz.json).

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-hand-fair --summary-only \
        --log "$(ls results/ftp1_final/*.jsonl | paste -sd,)" --summary-drain 1000:300,2000:1000
    python examples/cw2lm_final_report.py        # -> results/cw2lm_final/report_data.json, gain.png
    node examples/cw2lm_final_report.js          # -> docs/CW2L_FTP1_hand_grip_report.docx
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
args = sys.argv[1:] + [None] * 3
grip_path = args[0] or os.path.join(OUT, "cw2lm_ftp1_grip_hand_fair_20mhz.json")
ref_path = args[1] or os.path.join(OUT, "cw2lm_ftp1_fair_20mhz.json")
out_dir = args[2] or os.path.join(OUT, "cw2lm_final")
os.makedirs(out_dir, exist_ok=True)

VARIANT = "irc-fix-warmfast-pr-rtt4"
CASES = {"svd_sb_20ms": "Sub-band SVD", "svd_20ms": "Wideband SVD"}
LOADS = ("20", "50", "70")
SCHEMES = {"nr": "NR (1 CW)", "lte": "LTE style (≤ 2 CW)", "per_layer": "1 CW per layer"}
T975_9 = 2.262          # Student t, 97.5 %, 9 degrees of freedom


def cells(path):
    with open(path) as fh:
        summ = json.load(fh)
    return summ, {(e["case"], e["load"]): dict(e["variants"].get(VARIANT, {}), n_slots=e["n_slots"])
                  for e in summ["configurations"]}


def se(d):
    m = sum(d) / len(d)
    return (sum((x - m) ** 2 for x in d) / (len(d) - 1) / len(d)) ** 0.5


def cell(c):
    """The numbers of one precoding and load the report needs."""
    if not c or "nr" not in c:
        return None
    out = {"n_slots": c["n_slots"], "schemes": {}}
    for s in SCHEMES:
        v = c.get(s)
        if not v:
            continue
        row = dict(drops=len(v["drops"]), files=v["files"], ru=100 * v["ru"],
                   upt_mean=v["upt_mean"] / 1e6, upt_p5=v["upt_p5"] / 1e6,
                   upt_p50=v["upt_p50"] / 1e6, upt_p95=v["upt_p95"] / 1e6,
                   bler_cw=[100 * x for x in v["bler_first_cw"]], mean_rank=v["mean_rank"],
                   rank_hist=[100 * x for x in v["rank_hist"]],
                   retx=100 * v["retx_rbg_fraction"],
                   mod=[100 * x for x in (v.get("modulation_share") or [])])
        g = v.get("gain_vs_nr_pct")
        if s != "nr" and g:
            d = g["upt_mean_per_drop"]
            row.update(gain_mean=g["upt_mean"], gain_p5=g["upt_p5"], gain_p95=g["upt_p95"],
                       gain_drops=d, gain_se=se(d), gain_ci=T975_9 * se(d),
                       drops_pos=sum(x > 0 for x in d), drop_min=min(d), drop_max=max(d))
        out["schemes"][s] = row
    return out


summ, G = cells(grip_path)
_, R = cells(ref_path)
data = {"setup": {k: v for k, v in summ.items() if k != "configurations"},
        "cases": CASES, "loads": LOADS, "schemes": SCHEMES,
        "grip": {f"{c}|{ld}": cell(G.get((c, ld))) for c in CASES for ld in LOADS},
        "ref": {f"{c}|{ld}": cell(R.get((c, ld))) for c in CASES for ld in LOADS}}
for name in ("cw2lm_ftp1_grip_hand_fair_rates_20mhz.json", "cw2lm_ftp1_grip_drops.json"):
    p = os.path.join(OUT, name)
    if os.path.exists(p):
        with open(p) as fh:
            data[name.split(".")[0]] = json.load(fh)
with open(os.path.join(out_dir, "report_data.json"), "w") as fh:
    json.dump(data, fh, indent=1)

# --- figure: mean UPT gain over NR, the 10 single drops and the 95 % interval
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
COL = {"lte": "#2a78d6", "per_layer": "#eb6834"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})
fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.5), sharey=True)
for ax, case in zip(axes, CASES):
    for k, s in enumerate(("lte", "per_layer")):
        off = -0.2 if s == "lte" else 0.2
        for i, ld in enumerate(LOADS):
            c = data["grip"][f"{case}|{ld}"]
            if not c or s not in c["schemes"]:
                continue
            r = c["schemes"][s]
            x = i + off
            ax.scatter([x - 0.1] * len(r["gain_drops"]), r["gain_drops"], s=9, color=COL[s],
                       alpha=0.35, linewidths=0, zorder=2)
            ax.errorbar([x], [r["gain_mean"]], yerr=[r["gain_ci"]], color=COL[s], lw=2,
                        capsize=0, zorder=3)
            ax.scatter([x], [r["gain_mean"]], s=46, color=COL[s], edgecolors="white",
                       linewidths=1.2, zorder=4, label=SCHEMES[s] if i == 0 else None)
            ax.annotate(f"{r['gain_mean']:+.1f}".replace("-", "−"),
                        (x, r["gain_mean"] + r["gain_ci"]), xytext=(2, 4),
                        textcoords="offset points", ha="center", color=INK, fontsize=8.5,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85),
                        zorder=5)
    ax.axhline(0, color=MUTED, lw=0.8, zorder=1)
    ax.set_xticks(range(len(LOADS)), [f"{ld} % RU" for ld in LOADS])
    ax.set_xlim(-0.6, len(LOADS) - 0.45)
    ax.set_title(CASES[case], color=INK, fontsize=10, loc="left")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
axes[0].set_ylabel("Mean UPT gain over NR [%]")
fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", frameon=False, ncols=2,
           fontsize=8.5, labelcolor=INK, handletextpad=0.2, columnspacing=1.2,
           bbox_to_anchor=(0.995, 1.0))
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(os.path.join(out_dir, "gain.png"), dpi=220, facecolor="white")
print("wrote", os.path.normpath(out_dir))
