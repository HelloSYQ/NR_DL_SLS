#!/usr/bin/env python3
"""FTP model 1 at 20 MHz, OLLA warm + fast start, synchronous HARQ: without
(results/cw2lm_ftp1_warmfast_20mhz.json) and with the users' hand grip
(results/cw2lm_ftp1_grip_20mhz.json; TR 38.901 7.6.4.1 UT self-blocking,
portrait / landscape 50 / 50, random orientation, 30 dB per blocked cluster).
Each set runs at its own arrival rates for 20 / 50 / 70 % NR resource
utilisation (results/cw2lm_ftp1[_grip]_rates_20mhz.json), so the rate change
is the capacity cost of the grip at that load.  Gains are against NR of the
same set (MMSE-IRC; with one codeword SIC is MMSE-IRC).  The drop statistics
compare the 10 drops with and without the grip (same UTs, pathloss and
clusters; seed [1, drop]).

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip --summary-only \\
        --log <results/ftp1_grip/*.jsonl, comma-separated> \\
        --summary-drain 1000:300,2000:1000
    python examples/cw2lm_ftp1_grip_compare.py        # -> results/cw2lm_ftp1_grip_20mhz.md
"""
import dataclasses
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import cw2lm_ftp_eval as ev  # noqa: E402
from nrsls.engine.drop import generate_drop  # noqa: E402
from nrsls.propagation.blockage import LANDSCAPE, blocked_power_fraction  # noqa: E402
from nrsls.propagation.pathloss import LOS  # noqa: E402

OUT = os.path.join(HERE, "..", "results")
args = sys.argv[1:] + [None] * 3
base_path = args[0] or os.path.join(OUT, "cw2lm_ftp1_warmfast_20mhz.json")
grip_path = args[1] or os.path.join(OUT, "cw2lm_ftp1_grip_20mhz.json")
md_out = args[2] or os.path.join(OUT, "cw2lm_ftp1_grip_20mhz.md")
DROP_STATS = os.path.join(OUT, "cw2lm_ftp1_grip_drops.json")
CASES = ("svd_sb_20ms", "svd_20ms")
LOADS = ("20", "50", "70")
ROWS = (("irc-fix-warmfast", "nr", "NR"), ("irc-fix-warmfast", "lte", "LTE"),
        ("irc-fix-warmfast", "lte_twisted", "Twisted LTE"),
        ("irc-fix-warmfast", "per_layer", "1 CW per layer"),
        ("sic-fix-warmfast", "lte", "LTE, SIC"),
        ("sic-fix-warmfast", "per_layer", "1 CW per layer, SIC"))
KPI = ("upt_mean", "upt_p5", "upt_p95")


def drop_stats(n_drops=10, seed=1) -> dict:
    """Grip effect on the drops of the evaluation (cached in DROP_STATS)."""
    if os.path.exists(DROP_STATS):
        with open(DROP_STATS) as fh:
            return json.load(fh)
    base = ev.scenario("20mhz-ftp1")
    grip = ev.scenario("20mhz-ftp1-grip")
    assert dataclasses.replace(base, ue_self_blocking=True) == grip
    acc = {k: [] for k in ("loss_best", "loss_same", "lost_share", "moved", "geo0", "geo1",
                           "landscape", "cl_blocked", "los_blocked")}
    for d in range(n_drops):
        a = generate_drop(base, np.random.default_rng([seed, d]), keep_clusters=True)
        b = generate_drop(grip, np.random.default_rng([seed, d]), keep_clusters=True)
        u = np.arange(a.ues.n)
        best0, best1 = a.coupling_gain_db.max(axis=0), b.coupling_gain_db.max(axis=0)
        acc["loss_best"] += list(best0 - best1)                 # strongest cell, each side
        acc["loss_same"] += list(a.coupling_gain_db[a.serving_cell, u]
                                 - b.coupling_gain_db[a.serving_cell, u])
        site = b.layout.cell_site[b.serving_cell]
        for s in np.unique(site):
            m = site == s
            cl = b.clusters[s]
            acc["lost_share"] += list(blocked_power_fraction(cl)[u[m]])
            v = cl.valid[u[m]]
            acc["cl_blocked"].append([float(np.sum((cl.gain[u[m]] < 1) & v)), float(v.sum())])
            los = b.condition[s, u[m]] == LOS
            acc["los_blocked"].append([float(np.sum(cl.los_gain[u[m]][los] < 1)),
                                       float(los.sum())])
        acc["moved"] += list(a.serving_cell != b.serving_cell)
        acc["geo0"] += list(a.geometry_db)
        acc["geo1"] += list(b.geometry_db)
        acc["landscape"] += list(b.self_blocking.mode == LANDSCAPE)
    pct = lambda x, q: float(np.percentile(x, q))
    lb, ls = np.array(acc["loss_best"]), np.array(acc["loss_same"])
    g0, g1 = np.array(acc["geo0"]), np.array(acc["geo1"])
    cl, lo = np.array(acc["cl_blocked"]).sum(0), np.array(acc["los_blocked"]).sum(0)
    out = {"drops": n_drops, "uts": int(lb.size),
           "landscape_share": float(np.mean(acc["landscape"])),
           "serving_cluster_blocked_share": float(cl[0] / cl[1]),
           "los_ray_blocked_share": float(lo[0] / lo[1]) if lo[1] else None,
           "los_links": int(lo[1]),
           "serving_power_lost_share_mean": float(np.mean(acc["lost_share"])),
           "best_cell_loss_db": {"mean": float(lb.mean()), "p50": pct(lb, 50),
                                 "p90": pct(lb, 90), "max": float(lb.max())},
           "same_cell_loss_db": {"mean": float(ls.mean()), "p50": pct(ls, 50),
                                 "p90": pct(ls, 90), "max": float(ls.max())},
           "serving_cell_changed_share": float(np.mean(acc["moved"])),
           "geometry_db": {"no_grip": {"mean": float(g0.mean()), "p5": pct(g0, 5),
                                       "p50": pct(g0, 50), "p95": pct(g0, 95)},
                           "grip": {"mean": float(g1.mean()), "p5": pct(g1, 5),
                                    "p50": pct(g1, 50), "p95": pct(g1, 95)}}}
    with open(DROP_STATS, "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def cells(path):
    with open(path) as fh:
        return {(e["case"], e["load"]): e["variants"] for e in json.load(fh)["configurations"]}


def rates(path):
    with open(path) as fh:
        return {c: v["rates"] for c, v in json.load(fh).items()}


def main():
    B, G = cells(base_path), cells(grip_path)
    RB = rates(os.path.join(OUT, "cw2lm_ftp1_rates_20mhz.json"))
    RG = rates(os.path.join(OUT, "cw2lm_ftp1_grip_rates_20mhz.json"))
    ds = drop_stats()
    f = lambda x: f"{x:+.1f}".replace("-", "−")
    n = lambda x: f"{x:.1f}".replace("-", "−")
    bl, sl = ds["best_cell_loss_db"], ds["same_cell_loss_db"]
    g0, g1 = ds["geometry_db"]["no_grip"], ds["geometry_db"]["grip"]
    L = ["FTP model 1, 20 MHz / 44 dBm, OLLA warm + fast start, HARQ fix, synchronous HARQ, "
         "10 drops: without and with the users' hand grip (TR 38.901 7.6.4.1 UT self-blocking: "
         "portrait or landscape 50 / 50, random orientation that also turns the UT array, "
         "30 dB on each cluster whose centre arrives in the grip's region). Each set runs at "
         "its own arrival rates for 20 / 50 / 70 % NR resource utilisation; gains are against "
         "NR of the same set; 'own UPT' compares a scheme with itself across the sets, at the "
         "same RU target (the grip set carries less traffic there).", "",
         "## What the grip does to the drops", "",
         f"{ds['drops']} drops, {ds['uts']} UTs ({100 * ds['landscape_share']:.0f} % landscape).", "",
         "| Quantity | Value |", "|---|---|",
         f"| Serving-link clusters blocked | {100 * ds['serving_cluster_blocked_share']:.0f} % |",
         f"| Serving-link multipath power lost (mean share) | "
         f"{100 * ds['serving_power_lost_share_mean']:.0f} % |",
         f"| LOS ray blocked (LOS serving links, {ds['los_links']}) | "
         + (f"{100 * ds['los_ray_blocked_share']:.0f} % |" if ds["los_ray_blocked_share"] is not None
            else "— |"),
         f"| Loss toward the former serving cell [dB]: mean / median / p90 / max | "
         f"{n(sl['mean'])} / {n(sl['p50'])} / {n(sl['p90'])} / {n(sl['max'])} |",
         f"| Loss of the strongest cell after re-attachment [dB]: mean / median / p90 / max | "
         f"{n(bl['mean'])} / {n(bl['p50'])} / {n(bl['p90'])} / {n(bl['max'])} |",
         f"| UTs that change serving cell | {100 * ds['serving_cell_changed_share']:.0f} % |",
         f"| Geometry (full-load SINR) [dB], mean / p5 / p50 / p95: no grip → grip | "
         f"{n(g0['mean'])} / {n(g0['p5'])} / {n(g0['p50'])} / {n(g0['p95'])} → "
         f"{n(g1['mean'])} / {n(g1['p5'])} / {n(g1['p50'])} / {n(g1['p95'])} |", "",
         "## Arrival rates and NR", "",
         "| Precoder | Load | Rate [UTs/s/cell]: no grip → grip | RU | NR mean rank | "
         "NR UPT mean / p5 / p95 [Mbit/s]: no grip → grip | NR UPT change [%] |",
         "|---|---|---|---|---|---|---|"]
    for case in CASES:
        for load in LOADS:
            a = B.get((case, load), {}).get("irc-fix-warmfast", {}).get("nr")
            b = G.get((case, load), {}).get("irc-fix-warmfast", {}).get("nr")
            if not a or not b:
                continue
            ra, rb = RB[case][load], RG[case][load]
            mb = lambda st: " / ".join(f"{st[k] / 1e6:.1f}" for k in KPI)
            L.append(f"| {case} | {load} % | {ra:.2f} → {rb:.2f} ({f(100 * (rb / ra - 1))} %) | "
                     f"{100 * a['ru']:.0f} → {100 * b['ru']:.0f} % | "
                     f"{a['mean_rank']:.2f} → {b['mean_rank']:.2f} | {mb(a)} → {mb(b)} | "
                     + " / ".join(f(100 * (b[k] / a[k] - 1)) for k in KPI) + " |")
    L += ["", "## Gains against NR", ""]
    for case in CASES:
        for load in LOADS:
            if (case, load) not in B or (case, load) not in G:
                continue
            L += [f"### {case}, {load} % load", "",
                  "| Scheme | Drops | Mean rank | BLER per CW [%], grip | "
                  "Gain vs NR, mean / p5 / p95 [%]: no grip → grip | "
                  "Own UPT, grip vs no grip, mean / p5 / p95 [%] |",
                  "|---|---|---|---|---|---|"]
            for variant, scheme, name in ROWS:
                # NR of the SIC variants is the MMSE-IRC NR
                ref = "irc-fix-warmfast" if scheme == "nr" else variant
                a = B[(case, load)].get(ref, {}).get(scheme)
                b = G[(case, load)].get(ref, {}).get(scheme)
                if not a or not b:
                    continue
                if scheme == "nr" and variant != "irc-fix-warmfast":
                    continue
                cw = " / ".join(f"{100 * x:.1f}" for x in b["bler_first_cw"])
                ga, gb = a.get("gain_vs_nr_pct"), b.get("gain_vs_nr_pct")
                gain = ("—" if scheme == "nr" else " / ".join(f(ga[k]) for k in KPI) + " → "
                        + " / ".join(f(gb[k]) for k in KPI))
                own = " / ".join(f(100 * (b[k] / a[k] - 1)) for k in KPI)
                L.append(f"| {name} | {len(b['drops'])} | {a['mean_rank']:.2f} → "
                         f"{b['mean_rank']:.2f} | {cw} | {gain} | {own} |")
            L.append("")
    md = "\n".join(L)
    print(md)
    with open(md_out, "w") as fh:
        fh.write(md + "\n")
    print("wrote", os.path.normpath(md_out))


if __name__ == "__main__":
    main()
