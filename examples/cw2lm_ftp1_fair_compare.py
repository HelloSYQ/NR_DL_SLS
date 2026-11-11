#!/usr/bin/env python3
"""FTP model 1 at 20 MHz, MMSE-IRC: the warm + fast set
(results/cw2lm_ftp1_warmfast_20mhz.json, variant irc-fix-warmfast: one OLLA
loop per UT and codeword, 8-slot HARQ round trip) against the fair-baseline
rerun (results/cw2lm_ftp1_fair_20mhz.json, variant irc-fix-warmfast-pr-rtt4:
one loop per transmission rank and codeword for every scheme, NR too, and a
4-slot round trip).  Same 10 drops, arrivals and file counting (files that
arrived before the last 300 slots of a 1000-slot run, 1000 of a 2000-slot
run).

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1 --summary-only \
        --log "$(ls results/ftp1_fair/*.jsonl | paste -sd,)" \
        --out results/cw2lm_ftp1_fair_20mhz.json --summary-drain 1000:300,2000:1000
    python examples/cw2lm_ftp1_fair_compare.py          # -> results/cw2lm_ftp1_fair_20mhz.md
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
args = sys.argv[1:] + [None] * 3
paths = (args[0] or os.path.join(OUT, "cw2lm_ftp1_warmfast_20mhz.json"),
         args[1] or os.path.join(OUT, "cw2lm_ftp1_fair_20mhz.json"))
md_out = args[2] or os.path.join(OUT, "cw2lm_ftp1_fair_20mhz.md")
old, new = (json.load(open(p)) for p in paths)
V_OLD, V_NEW = "irc-fix-warmfast", "irc-fix-warmfast-pr-rtt4"
SCH = ("nr", "lte", "per_layer")
NAME = {"nr": "NR", "lte": "LTE", "per_layer": "1 CW per layer"}
CASE = {"svd_sb_20ms": "Sub-band SVD", "svd_20ms": "Wideband SVD"}
KPI = ("upt_mean", "upt_p5", "upt_p95")


def cells(summ, variant):
    return {(e["case"], e["load"]): e["variants"].get(variant, {}) for e in summ["configurations"]}


A, B = cells(old, V_OLD), cells(new, V_NEW)
f = lambda x: f"{x:+.1f}".replace("-", "−")
keys = [(c, ld) for c in CASE for ld in ("20", "50", "70") if B.get((c, ld), {}).get("nr")]

L = ["FTP model 1, 20 MHz / 44 dBm, MMSE-IRC, OLLA warm + fast start, HARQ refill fix, 10 drops.  "
     "Before: one OLLA loop per UT and codeword, 8-slot HARQ round trip.  Fair baseline: one "
     "loop per transmission rank and codeword for every scheme (NR: one per rank) and a 4-slot "
     "round trip.  Gains vs NR compare a scheme with NR under the same setting; 'own UPT' "
     "compares a scheme with itself across the two settings (same drops and arrivals).", "",
     "## Mean UPT gain over NR, fair baseline", "",
     "Mean over the files of all 10 drops, with the standard error of the 10 single-drop gains "
     "(paired drops) after the ±.", "",
     "| Precoding | Scheme | 20 % | 50 % | 70 % load | Single drops above zero |",
     "|---|---|---|---|---|---|"]
for case in CASE:
    for s in ("lte", "per_layer"):
        row, pos = [], []
        for ld in ("20", "50", "70"):
            g = B.get((case, ld), {}).get(s, {}).get("gain_vs_nr_pct")
            if g:
                d = g["upt_mean_per_drop"]
                m = sum(d) / len(d)
                se = (sum((x - m) ** 2 for x in d) / (len(d) - 1) / len(d)) ** 0.5
                row.append(f"{f(g['upt_mean'])} ± {se:.1f} %")
                pos.append(f"{sum(x > 0 for x in d)} of {len(d)}")
        if any(row):
            L.append(f"| {CASE[case]} | {NAME[s]} | " + " | ".join(row) + " | " + " / ".join(pos) + " |")
L += ["", "NR's resource utilisation in the fair baseline (the arrival rates are those calibrated "
      "for 20 / 50 / 70 % with plain OLLA and an 8-slot round trip; NR is 4–6 % faster here): "
      + "; ".join(f"{CASE[c]} " + " / ".join(f"{100 * B[(c, ld)]['nr']['ru']:.0f}" for ld in ("20", "50", "70")
                                             if (c, ld) in keys) + " %" for c in CASE) + ".", "",
      "The fair-baseline runs used a buffer-estimate cap of 7.406 instead of 7.4 bit per RE and "
      "layer (see docs/qam1024-50mhz.md).  12 of them were repeated with 7.4: 7 were identical, the "
      "other 5 moved a run's mean UPT by −0.5 to +0.02 %.", ""]
for case, load in keys:
    L += [f"### {CASE[case]}, {load} % load", "",
          "| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: "
          "before → fair | Mean gain of the single drops, fair [%] | "
          "Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |",
          "|---|---|---|---|---|---|---|"]
    for s in SCH:
        a, b = A.get((case, load), {}).get(s), B[(case, load)].get(s)
        if not b:
            continue
        bl = lambda st: " / ".join(f"{100 * x:.1f}" for x in st["bler_first_cw"]) if st else "—"
        ga = (a or {}).get("gain_vs_nr_pct", {})
        gb = b.get("gain_vs_nr_pct", {})
        if s == "nr":
            gain = drops = "—"
        else:
            gain = ((" / ".join(f(ga[k]) for k in KPI) if ga else "—") + " → "
                    + " / ".join(f(gb[k]) for k in KPI))
            d = gb["upt_mean_per_drop"]
            drops = f"{f(min(d))} to {f(max(d))} ({sum(x > 0 for x in d)} of {len(d)} above zero)"
        own = " / ".join(f(100 * (b[k] / a[k] - 1)) for k in KPI) if a else "—"
        L.append(f"| {NAME[s]} | {len(b['drops'])} | {bl(a)} → {bl(b)} | {gain} | {drops} | {own} "
                 f"| {b['mean_rank']:.2f} |")
    L.append("")
md = "\n".join(L)
print(md)
with open(md_out, "w") as fh:
    fh.write(md + "\n")
print("wrote", os.path.normpath(md_out))
