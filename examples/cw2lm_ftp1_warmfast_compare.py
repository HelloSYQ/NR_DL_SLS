#!/usr/bin/env python3
"""FTP model 1 at 20 MHz (MMSE-IRC + OLLA + HARQ fix): the published set
(results/cw2lm_ftp1_20mhz.json: plain OLLA, every loop starting at 0 dB;
variant irc-fix, NR irc-olla) against the rerun with OLLA warm + fast start
(results/cw2lm_ftp1_warmfast_20mhz.json, variant irc-fix-warmfast: a new
UT's loops start from the mean of the loops with at least 20 ACK/NACKs, and
a loop's first 20 ACK/NACKs move it x4; NR runs with both).  Both summaries
count the files that arrived before the last 300 (1000-slot runs) or 1000
(2000-slot runs) slots, on the same 10 drops and arrivals.

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1 --summary-only \
        --log <results/ftp1_warmfast/*.jsonl, comma-separated> \
        --out results/cw2lm_ftp1_warmfast_20mhz.json --summary-drain 1000:300,2000:1000
    python examples/cw2lm_ftp1_warmfast_compare.py      # -> results/cw2lm_ftp1_warmfast_20mhz.md
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
args = sys.argv[1:] + [None] * 3
paths = (args[0] or os.path.join(OUT, "cw2lm_ftp1_20mhz.json"),
         args[1] or os.path.join(OUT, "cw2lm_ftp1_warmfast_20mhz.json"))
md_out = args[2] or os.path.join(OUT, "cw2lm_ftp1_warmfast_20mhz.md")
pub, wf = (json.load(open(p)) for p in paths)
SCH = ("nr", "lte", "lte_twisted", "per_layer")
NAME = {"nr": "NR", "lte": "LTE", "lte_twisted": "Twisted LTE", "per_layer": "1 CW per layer"}
KPI = ("upt_mean", "upt_p5", "upt_p95")


def cells(summ):
    out = {}
    for e in summ["configurations"]:
        out[(e["case"], e["load"])] = e["variants"]
    return out


def pick(variants, scheme, which):
    if which == "pub":
        v = variants.get("irc-olla" if scheme == "nr" else "irc-fix", {})
    else:
        v = variants.get("irc-fix-warmfast", {})
    return v.get(scheme)


P, W = cells(pub), cells(wf)
f = lambda x: f"{x:+.1f}".replace("-", "−")
L = ["FTP model 1, 20 MHz / 44 dBm, MMSE-IRC + OLLA + HARQ fix, 10 drops.  Published: "
     "plain OLLA (loops start at 0 dB).  Warm + fast: a new UT's loops start from the mean "
     "of the loops with >= 20 ACK/NACKs and move x4 for their first 20 ACK/NACKs (NR too).  "
     "Gains vs NR compare each scheme with NR under the same link adaptation; 'own UPT' "
     "compares a scheme with itself across the two (same drops and arrivals).  Retx share: "
     "RBGs of retransmissions.", ""]
for case in ("svd_sb_20ms", "svd_20ms"):
    for load in ("20", "50", "70"):
        if (case, load) not in P or (case, load) not in W:
            continue
        L += [f"### {case}, {load} % load", "",
              "| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | "
              "Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | "
              "Own UPT, warm + fast vs published, mean / p5 / p95 [%] |",
              "|---|---|---|---|---|---|"]
        for s in SCH:
            a, b = pick(P[(case, load)], s, "pub"), pick(W[(case, load)], s, "wf")
            if not a or not b:
                continue
            bl = lambda st: " / ".join(f"{100 * x:.1f}" for x in st["bler_first_cw"])
            ga = a.get("gain_vs_nr_pct", {})
            gb = b.get("gain_vs_nr_pct", {})
            gain = ("—" if s == "nr" else
                    " / ".join(f(ga[k]) for k in KPI) + " → " + " / ".join(f(gb[k]) for k in KPI))
            own = " / ".join(f(100 * (b[k] / a[k] - 1)) for k in KPI)
            L.append(f"| {NAME[s]} | {len(b['drops'])} of {len(a['drops'])} | {bl(a)} → {bl(b)} | "
                     f"{100 * a['retx_rbg_fraction']:.1f} → {100 * b['retx_rbg_fraction']:.1f} % | "
                     f"{gain} | {own} |")
        L.append("")
md = "\n".join(L)
print(md)
with open(md_out, "w") as fh:
    fh.write(md + "\n")
print("wrote", os.path.normpath(md_out))
