#!/usr/bin/env python3
"""FTP model 1 at 20 MHz with OLLA warm + fast start: synchronous HARQ
(results/cw2lm_ftp1_warmfast_20mhz.json, variants irc-fix-warmfast and
sic-fix-warmfast) against asynchronous HARQ (results/cw2lm_ftp1_async_20mhz.json,
the same variants with -async: a due retransmission keeps priority but takes
the best free RBGs for the UT's current report).  Gains are against NR under
the same HARQ mode and OLLA (MMSE-IRC; with one codeword SIC is MMSE-IRC);
'own UPT' compares a scheme with itself across the two modes, on the same
drops and arrivals.

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1 --summary-only \\
        --log <results/ftp1_async/*.jsonl, comma-separated> \\
        --out results/cw2lm_ftp1_async_20mhz.json --summary-drain 1000:300,2000:1000
    python examples/cw2lm_ftp1_async_compare.py         # -> results/cw2lm_ftp1_async_20mhz.md
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
args = sys.argv[1:] + [None] * 3
sync_path = args[0] or os.path.join(OUT, "cw2lm_ftp1_warmfast_20mhz.json")
async_path = args[1] or os.path.join(OUT, "cw2lm_ftp1_async_20mhz.json")
md_out = args[2] or os.path.join(OUT, "cw2lm_ftp1_async_20mhz.md")
ROWS = (("irc-fix-warmfast", "nr", "NR"), ("irc-fix-warmfast", "lte", "LTE"),
        ("irc-fix-warmfast", "lte_twisted", "Twisted LTE"),
        ("irc-fix-warmfast", "per_layer", "1 CW per layer"),
        ("sic-fix-warmfast", "lte", "LTE, SIC"), ("sic-fix-warmfast", "per_layer",
                                                  "1 CW per layer, SIC"))
KPI = ("upt_mean", "upt_p5", "upt_p95")


def cells(path):
    with open(path) as fh:
        return {(e["case"], e["load"]): e["variants"] for e in json.load(fh)["configurations"]}


S, A = cells(sync_path), cells(async_path)
f = lambda x: f"{x:+.1f}".replace("-", "−")
L = ["FTP model 1, 20 MHz / 44 dBm, OLLA warm + fast start, HARQ fix, 10 drops: synchronous "
     "HARQ (a retransmission one round trip later on its own RBGs) against asynchronous HARQ "
     "(priority, on the best free RBGs for the current report). Gains are against NR under the "
     "same HARQ mode; 'own UPT' compares a scheme with itself across the modes. Moved: share "
     "of retransmissions sent on other RBGs. Retx share: RBGs of retransmissions.", ""]
for case in ("svd_sb_20ms", "svd_20ms"):
    for load in ("20", "50", "70"):
        if (case, load) not in S or (case, load) not in A:
            continue
        L += [f"### {case}, {load} % load", "",
              "| Scheme | Drops | BLER per CW [%]: sync → async | Retx share | Moved | "
              "Gain vs NR, mean / p5 / p95 [%]: sync → async | "
              "Own UPT, async vs sync, mean / p5 / p95 [%] |",
              "|---|---|---|---|---|---|---|"]
        for variant, scheme, name in ROWS:
            a = S[(case, load)].get(variant, {}).get(scheme)
            b = A[(case, load)].get(variant + "-async", {}).get(scheme)
            if not a or not b:
                continue
            bl = lambda st: " / ".join(f"{100 * x:.1f}" for x in st["bler_first_cw"])
            ga, gb = a.get("gain_vs_nr_pct"), b.get("gain_vs_nr_pct")
            gain = ("—" if scheme == "nr" else " / ".join(f(ga[k]) for k in KPI) + " → "
                    + " / ".join(f(gb[k]) for k in KPI))
            own = " / ".join(f(100 * (b[k] / a[k] - 1)) for k in KPI)
            L.append(f"| {name} | {len(b['drops'])} of {len(a['drops'])} | {bl(a)} → {bl(b)} | "
                     f"{100 * a['retx_rbg_fraction']:.1f} → {100 * b['retx_rbg_fraction']:.1f} % | "
                     f"{100 * b.get('retx_moved_fraction', 0.0):.0f} % | {gain} | {own} |")
        L.append("")
md = "\n".join(L)
print(md)
with open(md_out, "w") as fh:
    fh.write(md + "\n")
print("wrote", os.path.normpath(md_out))
