#!/usr/bin/env python3
"""FTP model 1 at 20 MHz with the users' hand grip and ideal CSI for every
transmission (cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-idealcsi: a fresh
RI / PMI / CQI report every slot, usable in the next slot, on a channel
refreshed every slot), MMSE-IRC with OLLA warm + fast start: NR, LTE split
and one codeword per layer with the eType-II codebook and with sub-band SVD,
at the arrival rates that give NR 20 / 50 / 70 % RU with ideal CSI.  Sub-band
SVD is also set against the realistic-CSI grip set (20 ms CSI, 4 ms old;
results/cw2lm_ftp1_grip_20mhz.json), which has no eType-II case.

    python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-idealcsi --summary-only \\
        --log <results/ftp1_idealcsi/*.jsonl, comma-separated> \\
        --summary-drain 1000:300,2000:1000
    python examples/cw2lm_ftp1_idealcsi_report.py   # -> results/cw2lm_ftp1_grip_idealcsi_20mhz.md
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
args = sys.argv[1:] + [None] * 3
ideal_path = args[0] or os.path.join(OUT, "cw2lm_ftp1_grip_idealcsi_20mhz.json")
real_path = args[1] or os.path.join(OUT, "cw2lm_ftp1_grip_20mhz.json")
md_out = args[2] or os.path.join(OUT, "cw2lm_ftp1_grip_idealcsi_20mhz.md")
RATES = os.path.join(OUT, "cw2lm_ftp1_grip_idealcsi_rates_20mhz.json")
VARIANT = "irc-fix-warmfast"
CASES = (("etype2_ideal", "eType-II codebook"), ("svd_sb_ideal", "Sub-band SVD"))
LOADS = ("20", "50", "70")
SCHEMES = (("nr", "NR"), ("lte", "LTE split"), ("per_layer", "1 CW per layer"))
KPI = (("upt_p5", "5th-percentile UPT"), ("upt_mean", "Mean UPT"),
       ("upt_p95", "95th-percentile UPT"))


def cells(path):
    with open(path) as fh:
        return {(e["case"], e["load"]): e["variants"] for e in json.load(fh)["configurations"]}


def main():
    I = cells(ideal_path)
    R = cells(real_path) if os.path.exists(real_path) else {}
    with open(RATES) as fh:
        rates = {c: v["rates"] for c, v in json.load(fh).items()}
    f = lambda x: f"{x:+.1f}".replace("-", "−")
    L = ["FTP model 1, 20 MHz / 44 dBm, hand grip (TR 38.901 UT self-blocking), MMSE-IRC, "
         "OLLA warm + fast start, HARQ fix, 10 drops, ideal CSI for every transmission: a fresh "
         "RI / PMI / CQI report every 0.5 ms slot, usable in the next slot, on a channel "
         "refreshed every slot. Arrival rates give NR 20 / 50 / 70 % RU with ideal CSI. "
         "Gains are against NR of the same precoder, load and drops.", ""]
    for case, name in CASES:
        if not all((case, ld) in I for ld in LOADS):
            continue
        nr = {ld: I[(case, ld)][VARIANT]["nr"] for ld in LOADS}
        L += [f"## {name}", "",
              "Arrival rate [UTs/s per cell]: " + " / ".join(f"{rates[case][ld]:.2f}" for ld in LOADS)
              + "; measured NR RU: " + " / ".join(f"{100 * nr[ld]['ru']:.0f}" for ld in LOADS)
              + " %; NR mean rank " + " / ".join(f"{nr[ld]['mean_rank']:.2f}" for ld in LOADS)
              + ".", "",
              "| UPT | Scheme | 20 % RU | 50 % RU | 70 % RU |", "|---|---|---|---|---|"]
        for k, kname in KPI:
            for s, sname in SCHEMES:
                row = []
                for ld in LOADS:
                    st = I[(case, ld)][VARIANT][s]
                    if s == "nr":
                        row.append(f"{st[k] / 1e6:.1f} Mbit/s")
                    else:
                        g = st["gain_vs_nr_pct"]
                        assert st["nr_reference"] == VARIANT and len(g["drops"]) == 10
                        row.append(f"{st[k] / 1e6:.1f} Mbit/s ({f(g[k])} %)")
                L.append(f"| {kname} | {sname} | " + " | ".join(row) + " |")
        L += ["", "First-transmission BLER per codeword [%] and mean rank:", "",
              "| Scheme | 20 % RU | 50 % RU | 70 % RU |", "|---|---|---|---|"]
        for s, sname in SCHEMES:
            row = []
            for ld in LOADS:
                st = I[(case, ld)][VARIANT][s]
                row.append(" / ".join(f"{100 * x:.1f}" for x in st["bler_first_cw"])
                           + f"; rank {st['mean_rank']:.2f}")
            L.append(f"| {sname} | " + " | ".join(row) + " |")
        L.append("")
    # sub-band SVD: ideal against realistic CSI (both with the grip)
    if R and all(("svd_sb_ideal", ld) in I and ("svd_sb_20ms", ld) in R for ld in LOADS):
        L += ["## Sub-band SVD: ideal CSI against 20 ms CSI (4 to 24 ms old)", "",
              "Each set at its own rates for 20 / 50 / 70 % NR RU.", "",
              "| Scheme | KPI | Gain vs NR [%], 20 ms CSI → ideal CSI, 20 / 50 / 70 % RU | "
              "Own UPT, ideal vs 20 ms CSI [%] |", "|---|---|---|---|"]
        for s, sname in SCHEMES:
            for k, kname in KPI:
                a = [R[("svd_sb_20ms", ld)][VARIANT][s] for ld in LOADS]
                b = [I[("svd_sb_ideal", ld)][VARIANT][s] for ld in LOADS]
                gain = "—" if s == "nr" else (
                    " / ".join(f(x["gain_vs_nr_pct"][k]) for x in a) + " → "
                    + " / ".join(f(x["gain_vs_nr_pct"][k]) for x in b))
                own = " / ".join(f(100 * (y[k] / x[k] - 1)) for x, y in zip(a, b))
                L.append(f"| {sname} | {kname} | {gain} | {own} |")
        L.append("")
    md = "\n".join(L)
    print(md)
    with open(md_out, "w") as fh:
        fh.write(md + "\n")
    print("wrote", os.path.normpath(md_out))


if __name__ == "__main__":
    main()
