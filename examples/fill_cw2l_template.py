#!/usr/bin/env python3
"""Fill the 'SLS rank 1-4' sheet of the 6GR CW2L result-collection template
with the FTP evaluation (examples/cw2lm_ftp_eval.py).

Two columns: D = MMSE-IRC receiver, E = codeword-level MMSE-SIC receiver,
both with OLLA per codeword.  Results go to the 'Type II codebook' block
(eType-II) and the 'Reciprocity based precoding' block (sub-band SVD); the
Type I and 'Other precoding scheme' blocks and the rows for Alt1 with a
different modulation order per layer stay empty (not evaluated).  Alt1 with
the same modulation order is the NR mapping, the baseline (0 %).  Gains are
written as fractions with a 0.0 % format.  Rows are found by their labels.

    python examples/fill_cw2l_template.py [results/cw2lm_ftp.json] \\
        [6GR_DL_CW2L_template_v003.xlsx]
"""

from __future__ import annotations

import json
import os
import sys

import openpyxl

ROOT = os.path.join(os.path.dirname(__file__), "..")
SHEET = "SLS rank 1-4"
COLS = {"irc-olla": "D", "sic-olla": "E"}
BLOCKS = {"Type II codebook": "etype2_20ms", "Reciprocity based precoding": "svd_sb_20ms"}
METRICS = {"Mean UPT": "upt_mean", "5th-percentile UPT": "upt_p5",
           "95th-percentile UPT": "upt_p95"}
ALTS = {"Alt1: 1 CW for rank 1-4, same modulation": "nr",
        "Alt2:": "lte", "Alt3:": "per_layer"}
LOADS = {"20%RU": "20", "50%RU": "50", "70%RU": "70"}

COMMON = {
    "Source Tdoc": "No Tdoc: nrsls system-level simulator (HelloSYQ/NR_DL_SLS, "
                   "docs/cw2lm-ftp.md)",
    "Network layout": "Hexagonal grid, 19 sites x 3 sectors (57 cells), ISD 200 m, "
                      "wrap-around",
    "Scenario": "Dense Urban-eMBB, ITU-R M.2412 configuration A; TR 38.901 UMa channel; "
                "80 % indoor (20 % high-loss / 80 % low-loss O2I), 20 % outdoor in cars",
    "Carrier, SCS and bandwidth": "4 GHz FDD, 15 kHz SCS, 10 MHz (52 PRB)",
    "UEs per cell": "10",
    "UE speed": "3 km/h indoor, 30 km/h in car",
    "NW antenna configuration": "32T: (M, N, P, Mg, Ng; Mp, Np) = (8, 8, 2, 1, 1; 2, 8), "
                                "0.5 lambda spacing, 8 dBi element, BS height 25 m",
    "UE antenna configuration": "4R: (M, N, P) = (1, 2, 2)",
    "UE noise figure": "7 dB",
    "UE blockage": "Not modelled",
    "gNB transmit power": "41 dBm per 10 MHz",
    "DL precoding method": "Codebook based (Rel-16 eType-II) and reciprocity based "
                           "(ideal sub-band SVD); SU-MIMO, rank <= 4",
    "CSI-RS periodicity": "20 ms",
    "CSI feedback delay": "4 ms",
    "CSI-RS channel estimation": "Ideal",
    "Number of CSI-RS ports": "32",
    "Precoding algorithm|Codebook based precoding":
        "Rel-16 eType-II PMI, parameter combination 6, 4-PRB sub-bands; RI <= 4; "
        "CQI per codeword",
    "SRS periodicity": "20 ms (the precoder is 4 ms old when used)",
    "SRS configuration": "All 4 UE ports sounded (antenna switching assumed), full band",
    "SRS channel estimation": "Ideal",
    "IPN acquisition assumption": "Ideal: precoder from the UE's whitened channel "
                                  "(interference covariance known); RI and per-codeword "
                                  "CQI reported by the UE",
    "Precoding algorithm|Reciprocity based precoding":
        "Unquantised sub-band SVD (dominant right singular vectors per 4-PRB sub-band)",
    "MCS table": "256QAM (TS 38.214 Table 5.1.3.1-2)",
    "SU-MIMO or MU-MIMO": "SU-MIMO",
    "PDSCH resource allocation / DMRS configuration":
        "PF scheduling per 4-PRB RBG, buffer-aware; 2 PDCCH symbols, 12 PDSCH symbols; "
        "DM-RS type 1, 1 front-loaded + 1 additional symbol (24 RE/PRB); 9 RE/PRB other "
        "overhead",
    "PDSCH DMRS channel estimation": "Ideal",
}
PER_COL = {
    "UE receiver": {
        "irc-olla": "MMSE-IRC",
        "sic-olla": "Codeword-level MMSE-SIC: codewords decoded in index order, decoded "
                    "codewords cancelled ideally, a failed codeword is not cancelled "
                    "(error propagation); CQI and RI computed for SIC. One codeword: "
                    "MMSE-IRC"},
    "Link adaptation and HARQ assumption": {
        k: "CQI per codeword (MIESM) with OLLA per UE and codeword (10 % BLER target, "
           "0.5 dB step)" + (", counting every NACK including SIC error propagation"
                             if k == "sic-olla" else "")
           + "; up to 4 transmissions, chase combining, 8-slot RTT; HARQ per codeword "
             "(failed codewords resent, decoded ones refilled with new TBs); "
             "retransmissions re-precoded with the latest report"
        for k in COLS},
    "Rank adaptation assumption": {
        k: "UE-selected RI <= 4 maximising the sum over codewords of layers x SE(wideband "
           "CQI), knowing the codeword split" + (" and SIC" if k == "sic-olla" else "")
        for k in COLS},
}


def _assumption(label: str, parent: str, traffic: str, remarks: str) -> dict:
    """{column key: text} of an assumption row, matched on the start of its
    label ('Precoding algorithm' also on the block it belongs to)."""
    for key, v in COMMON.items():
        name, _, blk = key.partition("|")
        if label.startswith(name) and (not blk or blk == parent):
            return {k: v for k in COLS}
    for key, v in PER_COL.items():
        if label.startswith(key):
            return v
    if label.startswith("Traffic model"):
        return {k: traffic for k in COLS}
    if label.startswith("Additional remarks"):
        return {k: remarks for k in COLS}
    return {}


def _text(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def fill(summ: dict, path: str) -> None:
    wb = openpyxl.load_workbook(path)
    ws = wb[SHEET]
    conf = {(e["case"], e["load"]): e for e in summ["configurations"]}

    # measured RU of NR per case and load, for the remarks
    ru = {c: "/".join(f"{100 * conf[(c, ld)]['variants']['irc-olla']['nr']['ru']:.0f}"
                      for ld in ("20", "50", "70") if (c, ld) in conf)
          for c in BLOCKS.values()}
    drops = sorted({d for e in summ["configurations"]
                    for v in e["variants"].values() for s in v.values() for d in s["drops"]})
    e0 = summ["configurations"][0]
    remarks = (
        "MIESM link abstraction. Alt2 = LTE split {1}/{1,1}/{1,2}/{2,2} (TS 36.211 Table "
        "6.3.3.2-1); Alt3 = one codeword per layer. Alt1 with the same modulation order is "
        "the NR baseline (0 %); Alt1 with a different modulation order per layer, Type I and "
        f"other precoding not evaluated. {len(drops)} drops of {e0['n_slots']} ms "
        f"({e0['warmup']} ms warm-up; files arriving in the last {e0['drain']} ms are "
        "served but not counted; files still open at the end count with an upper-bound "
        f"UPT). Measured NR RU [%] at the three loads: eType-II {ru['etype2_20ms']}, "
        f"sub-band SVD {ru['svd_sb_20ms']}; every scheme runs with the same files.")
    traffic = ("FTP model 3: 0.5 Mbyte files, Poisson arrivals per UE; arrival rates set so "
               "that NR with MMSE-IRC has 20 / 50 / 70 % RU in each precoding case")

    for col_key, col in COLS.items():
        ws[f"{col}2"] = {"irc-olla": "nrsls, MMSE-IRC",
                         "sic-olla": "nrsls, CW-level SIC"}[col_key]

    a_label = b_label = block = metric = alt = None
    for r in range(3, ws.max_row + 1):
        a, b, c = (_text(ws.cell(r, i).value) for i in (1, 2, 3))
        if a:
            a_label = a
        if b:
            b_label = b
        # a results block opens with a header row (no sub-label in column B);
        # 'Reciprocity based precoding' also labels assumption rows 21-25
        if not b and a in ("Type I codebook", "Type II codebook",
                           "Reciprocity based precoding", "Other precoding scheme"):
            block, metric, alt = a, None, None
            continue
        if block is None:                                  # assumption rows
            vals = _assumption(b_label if b else a_label, a_label, traffic, remarks)
            for k, v in vals.items():
                ws[f"{COLS[k]}{r}"] = v
            continue
        if block not in BLOCKS:
            continue
        metric = next((m for t, m in METRICS.items() if a_label.startswith(t)), None)
        alt = next((s for t, s in ALTS.items() if b_label.startswith(t)), None)
        load = LOADS.get(c.replace(" ", ""))
        if metric is None or alt is None or load is None:
            continue
        e = conf.get((BLOCKS[block], load))
        for k, col in COLS.items():
            cell = ws[f"{col}{r}"]
            if alt == "nr":
                cell.value = 0.0
            elif e and alt in e["variants"].get(k, {}):
                g = e["variants"][k][alt].get("gain_vs_nr_pct")
                if g:
                    cell.value = round(g[metric] / 100, 4)
            else:
                continue
            cell.number_format = "0.0%"
    wb.save(path)


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results", "cw2lm_ftp.json")
    xlsx = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT,
                                                              "6GR_DL_CW2L_template_v003.xlsx")
    with open(src) as fh:
        fill(json.load(fh), xlsx)
    print("filled", os.path.normpath(xlsx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
