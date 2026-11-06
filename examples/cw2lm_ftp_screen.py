#!/usr/bin/env python3
"""Screen of the multi-codeword HARQ fix and the rank-adaptation options A
and B for one codeword per layer (Alt 3), 20 MHz FTP set-up, against NR.
See docs/cw2lm-ftp-screen.md.

Reads the screen logs (results/ftp20_screen/*.jsonl) and the published
10-drop logs (results/ftp20_parts/*.jsonl), keeps the drops every variant
has (0-4 by default), and reports per precoder and load the UPT gain over
the matched NR run (cw2lm_ftp_eval.nr_reference: NR with B for the -b
variants) and whether it meets the target: mean and 95th percentile
>= +5 %, 5th percentile >= 0 %.

    python examples/cw2lm_ftp_screen.py                # table + results/cw2lm_ftp_screen_20mhz.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import cw2lm_ftp_eval as ev                                        # noqa: E402
from cw2lm_rank4_eval import load_log                              # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
ROWS = ("irc-olla", "irc-fix", "irc-fix-b", "sic-olla", "sic-fix", "sic-fix-a",
        "sic-fix-b", "sic-fix-ab")
TARGET = {"upt_mean": 5.0, "upt_p95": 5.0, "upt_p5": 0.0}
LABEL = {"irc-olla": "MMSE-IRC, published", "irc-fix": "MMSE-IRC + fix",
         "irc-fix-b": "MMSE-IRC + fix + B", "sic-olla": "SIC, published",
         "sic-fix": "SIC + fix", "sic-fix-a": "SIC + fix + A",
         "sic-fix-b": "SIC + fix + B", "sic-fix-ab": "SIC + fix + A + B"}


def screen(log: list, drops: set) -> dict:
    log = [r for r in log if r["drop"] in drops and r.get("setup") == "20mhz"]
    summ = ev.summarize(log, "20mhz")
    out = {"drops": sorted(drops), "target_pct": TARGET, "cells": []}
    for e in summ["configurations"]:
        v = e["variants"]
        cell = {"case": e["case"], "load": e["load"], "rows": {}}
        nr, nrb = v.get("irc-olla", {}).get("nr"), v.get("irc-fix-b", {}).get("nr")
        if nr:
            cell["nr"] = {k: nr[k] for k in ("ru", "upt_mean", "upt_p5", "upt_p95",
                                              "bler_first", "mean_rank", "retx_rbg_fraction")}
        if nr and nrb:                # what B does for NR itself
            cell["nr_b_vs_nr_pct"] = {k: ev._pct(nrb[k], nr[k])
                                      for k in ("upt_mean", "upt_p5", "upt_p95")}
            cell["nr_b"] = {k: nrb[k] for k in ("ru", "bler_first", "mean_rank")}
        for name in ROWS:
            st = v.get(name, {}).get("per_layer")
            if not st or "gain_vs_nr_pct" not in st:
                continue
            g = st["gain_vs_nr_pct"]
            cell["rows"][name] = {
                "drops": g["drops"], "nr_reference": st["nr_reference"],
                "gain_pct": {k: g[k] for k in TARGET},
                "meets_target": all(g[k] >= t for k, t in TARGET.items()),
                "ru": st["ru"], "retx_rbg_fraction": st["retx_rbg_fraction"],
                "bler_first_cw": st["bler_first_cw"], "mean_rank": st["mean_rank"],
                "rank_hist": st["rank_hist"],
                "upt_mean_per_drop_gain_pct": g["upt_mean_per_drop"]}
        out["cells"].append(cell)
    return out


def table(res: dict) -> str:
    f = lambda x: f"{x:+.1f}".replace("-", "−")
    L = [f"Drops {res['drops'][0]}-{res['drops'][-1]}. Gain of one codeword per layer over "
         "NR (MMSE-IRC; NR with B for the + B rows), UPT mean / 5th / 95th percentile [%]; "
         "✓ = mean and p95 >= +5 %, p5 >= 0 %.", ""]
    for cell in res["cells"]:
        L += [f"### {cell['case']}, {cell['load']} % RU", "",
              "| Variant | Mean | p5 | p95 | Target | RU | Retx share | First BLER per CW | "
              "Mean rank |", "|---|---|---|---|---|---|---|---|---|"]
        if "nr" in cell:
            n = cell["nr"]
            L.append(f"| NR (reference) | | | | | {100 * n['ru']:.0f} % | "
                     f"{100 * n['retx_rbg_fraction']:.1f} % | {100 * n['bler_first']:.1f} | "
                     f"{n['mean_rank']:.2f} |")
        if "nr_b_vs_nr_pct" in cell:
            g = cell["nr_b_vs_nr_pct"]
            L.append(f"| NR + B vs NR | {f(g['upt_mean'])} | {f(g['upt_p5'])} | "
                     f"{f(g['upt_p95'])} | | {100 * cell['nr_b']['ru']:.0f} % | | "
                     f"{100 * cell['nr_b']['bler_first']:.1f} | "
                     f"{cell['nr_b']['mean_rank']:.2f} |")
        for name, r in cell["rows"].items():
            g = r["gain_pct"]
            L.append(f"| {LABEL[name]} | {f(g['upt_mean'])} | {f(g['upt_p5'])} | "
                     f"{f(g['upt_p95'])} | {'✓' if r['meets_target'] else ''} | "
                     f"{100 * r['ru']:.0f} % | {100 * r['retx_rbg_fraction']:.1f} % | "
                     + " / ".join(f"{100 * b:.0f}" for b in r["bler_first_cw"])
                     + f" | {r['mean_rank']:.2f} |")
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=",".join(
        sorted(glob.glob(os.path.join(OUT, "ftp20_screen", "*.jsonl")))
        + sorted(glob.glob(os.path.join(OUT, "ftp20_parts", "*.jsonl")))))
    ap.add_argument("--drops", default="0,1,2,3,4")
    ap.add_argument("--out", default=os.path.join(OUT, "cw2lm_ftp_screen_20mhz"))
    args = ap.parse_args()
    res = screen(load_log(args.logs), {int(d) for d in args.drops.split(",")})
    md = table(res)
    print(md)
    with open(args.out + ".json", "w") as fh:
        json.dump(res, fh, indent=1)
    with open(args.out + ".md", "w") as fh:
        fh.write(md + "\n")
    print("wrote", os.path.normpath(args.out) + ".json/.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
