#!/usr/bin/env python3
"""Screen of the multi-codeword HARQ fix and the rank-adaptation options A
and B for one codeword per layer (Alt 3), 20 MHz FTP set-up, against NR.
See docs/cw2lm-ftp-screen.md.

Reads the screen logs (results/ftp20_screen/*.jsonl) and the published
10-drop logs (results/ftp20_parts/*.jsonl), keeps the drops every variant
has (0-4 by default), and reports per precoder and load the UPT gain over
NR and over NR with B (irc-fix-b), and whether the gain over the better of
the two for each KPI (each scheme at its best) meets the target: mean and
95th percentile >= +5 %, 5th percentile >= 0 %.

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
    """Per (precoder, load): every Alt 3 variant against NR (MMSE-IRC) and
    NR with B, on the drops both have.  The target is checked against the
    better NR run for each KPI (each scheme at its best)."""
    by = {}
    for r in log:
        if r["drop"] in drops and r.get("setup") == "20mhz" and r["load"] in ev.LOADS:
            key = (r["case"], r["load"], r["variant"], r["scheme"])
            by.setdefault(key, {})[r["drop"]] = r
    out = {"drops": sorted(drops), "target_pct": TARGET, "cells": []}
    for case in ev.CASES:
        for load in ev.LOADS:
            refs = {name: by.get((case, load, name, "nr"), {})
                    for name in ("irc-olla", "irc-fix-b")}
            if not refs["irc-olla"]:
                continue
            cell = {"case": case, "load": load, "rows": {}}
            nr = ev._kpis([refs["irc-olla"][d] for d in sorted(refs["irc-olla"])])
            cell["nr"] = {k: nr[k] for k in ("drops", "ru", "upt_mean", "upt_p5", "upt_p95",
                                              "bler_first", "mean_rank",
                                              "retx_rbg_fraction")}
            common = sorted(set(refs["irc-olla"]) & set(refs["irc-fix-b"]))
            if common:
                a = ev._kpis([refs["irc-olla"][d] for d in common])
                b = ev._kpis([refs["irc-fix-b"][d] for d in common])
                cell["nr_b"] = {"drops": common, "ru": b["ru"], "bler_first": b["bler_first"],
                                "mean_rank": b["mean_rank"],
                                "vs_nr_pct": {k: ev._pct(b[k], a[k]) for k in TARGET}}
            for name in ROWS:
                recs = by.get((case, load, name, "per_layer"), {})
                if not recs:
                    continue
                st = ev._kpis([recs[d] for d in sorted(recs)])
                row = {"drops": sorted(recs), "ru": st["ru"],
                       "retx_rbg_fraction": st["retx_rbg_fraction"],
                       "bler_first_cw": st["bler_first_cw"], "mean_rank": st["mean_rank"],
                       "rank_hist": st["rank_hist"], "gain_pct": {}}
                for ref, ref_recs in refs.items():
                    c = sorted(set(recs) & set(ref_recs))
                    if not c:
                        continue
                    m = ev._kpis([recs[d] for d in c])
                    n = ev._kpis([ref_recs[d] for d in c])
                    row["gain_pct"][ref] = {"drops": c, **{k: ev._pct(m[k], n[k])
                                                          for k in TARGET}}
                g = row["gain_pct"]
                row["vs_best_nr_pct"] = {k: min(v[k] for v in g.values()) for k in TARGET}
                row["meets_target"] = all(row["vs_best_nr_pct"][k] >= t
                                          for k, t in TARGET.items())
                row["complete"] = sorted(recs) == sorted(drops) and all(
                    v["drops"] == sorted(drops) for v in g.values())
                cell["rows"][name] = row
            out["cells"].append(cell)
    return out


def table(res: dict) -> str:
    f = lambda x: f"{x:+.1f}".replace("-", "−")
    L = [f"Drops {res['drops'][0]}-{res['drops'][-1]}. UPT gain of one codeword per layer "
         "over the better of NR and NR with B for each KPI (mean / 5th / 95th percentile "
         "[%]); ✓ = mean and p95 >= +5 %, p5 >= 0 %. The last column is the mean gain over "
         "NR with B. * = not all drops yet.", ""]
    for cell in res["cells"]:
        n = cell["nr"]
        L += [f"### {cell['case']}, {cell['load']} % RU", "",
              "| Variant | Mean | p5 | p95 | Target | RU | Retx share | First BLER per CW [%] "
              "| Mean rank | Mean vs NR + B |", "|---|---|---|---|---|---|---|---|---|---|",
              f"| NR | | | | | {100 * n['ru']:.0f} % | {100 * n['retx_rbg_fraction']:.1f} % | "
              f"{100 * n['bler_first']:.1f} | {n['mean_rank']:.2f} | |"]
        if "nr_b" in cell:
            b = cell["nr_b"]
            g = b["vs_nr_pct"]
            L.append(f"| NR + B, vs NR | {f(g['upt_mean'])} | {f(g['upt_p5'])} | "
                     f"{f(g['upt_p95'])} | | {100 * b['ru']:.0f} % | | "
                     f"{100 * b['bler_first']:.1f} | {b['mean_rank']:.2f} | |")
        for name, r in cell["rows"].items():
            g = r["vs_best_nr_pct"]
            gb = r["gain_pct"].get("irc-fix-b")
            L.append(f"| {LABEL[name]}{'' if r['complete'] else ' *'} | {f(g['upt_mean'])} | "
                     f"{f(g['upt_p5'])} | {f(g['upt_p95'])} | "
                     f"{'✓' if r['meets_target'] else ''} | {100 * r['ru']:.0f} % | "
                     f"{100 * r['retx_rbg_fraction']:.1f} % | "
                     + " / ".join(f"{100 * x:.0f}" for x in r["bler_first_cw"])
                     + f" | {r['mean_rank']:.2f} | {f(gb['upt_mean']) if gb else ''} |")
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
