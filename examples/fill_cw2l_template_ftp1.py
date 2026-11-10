#!/usr/bin/env python3
"""Fill the 20 MHz copy of the 6GR CW2L template ('SLS rank 1-4') with the
FTP model 1 evaluation with OLLA warm + fast start (examples/cw2lm_ftp_eval.py
--setup 20mhz-ftp1, variants irc-fix-warmfast and sic-fix-warmfast; summary
results/cw2lm_ftp1_warmfast_20mhz.json).

Three columns, each with its own assumption rows:
  D  MMSE-IRC (irc-fix-warmfast): Alt2 = LTE split, Alt3 = one CW per layer
  E  codeword-level SIC (sic-fix-warmfast): the same two mappings
  F  MMSE-IRC with Alt2 = twisted LTE (rank 4 = {layer 0} + {layers 1-3});
     its Alt3 rows stay empty
Blocks: 'Reciprocity based precoding' = sub-band SVD, 'Other precoding
scheme' = wideband SVD; the Type I and Type II codebook blocks are left empty
(not evaluated; values from an earlier fill are cleared).  Alt1 with the same
modulation order is the NR baseline (0 %), NR with MMSE-IRC and the same OLLA
for every column (with one codeword SIC is MMSE-IRC); Alt1 with a different
modulation order per layer is not evaluated.  Gains are written as fractions
with a 0.0 % format.  Every row of the sheet's table gets a cell in each
column, empty where there is no value, so a new column takes the borders and
formats of the one to its left.  Rows are found by their labels; the values
are written by patching the sheet's XML (fill_cw2l_template.write_cells), so
the rest of the workbook is left exactly as it was.

    python examples/fill_cw2l_template_ftp1.py \\
        [results/cw2lm_ftp1_warmfast_20mhz.json] [6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx]

The set with the users' hand grip (--setup 20mhz-ftp1-grip, TR 38.901
7.6.4.1 UT self-blocking) fills its own copy of the blank template, MMSE-IRC
only (--columns D); the summary's set-up switches the header, UE blockage,
source, traffic and remarks texts to the grip:

    git show b56a456:6GR_DL_CW2L_template_v003.xlsx > 6GR_DL_CW2L_template_v003_20MHz_44dBm_grip.xlsx
    python examples/fill_cw2l_template_ftp1.py results/cw2lm_ftp1_grip_20mhz.json \\
        6GR_DL_CW2L_template_v003_20MHz_44dBm_grip.xlsx --columns D
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(__file__))
from fill_cw2l_template import SHEET, _text, write_cells  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
# column -> (header, variant, {template alternative: scheme or None})
COLS = {
    "D": ("nrsls, MMSE-IRC", "irc-fix-warmfast",
          {"nr": "nr", "lte": "lte", "per_layer": "per_layer"}),
    "E": ("nrsls, CW-level SIC", "sic-fix-warmfast",
          {"nr": "nr", "lte": "lte", "per_layer": "per_layer"}),
    "F": ("nrsls, MMSE-IRC, Alt2 = twisted LTE", "irc-fix-warmfast",
          {"nr": "nr", "lte": "lte_twisted", "per_layer": None}),
}
NR_VARIANT = "irc-fix-warmfast"
BLOCKS = {"Type I codebook": None, "Type II codebook": None,
          "Reciprocity based precoding": "svd_sb_20ms", "Other precoding scheme": "svd_20ms"}
METRICS = {"Mean UPT": "upt_mean", "5th-percentile UPT": "upt_p5",
           "95th-percentile UPT": "upt_p95"}
ALTS = {"Alt1: 1 CW for rank 1-4, same modulation": "nr",
        "Alt1: 1 CW for rank 1-4, different modulation": None,
        "Alt2:": "lte", "Alt3:": "per_layer"}
LOADS = {"20%RU": "20", "50%RU": "50", "70%RU": "70"}
LOAD_ORDER = ("20", "50", "70")
# set-ups evaluated with the users' hand grip (UT self-blocking)
GRIP_SETUPS = ("20mhz-ftp1-grip",)
GRIP_BLOCKAGE = ("Self-blocking (hand grip), TR 38.901 7.6.4.1 blockage model A without the "
                 "non-self blockers: each UE is held in portrait (one hand) or landscape (two "
                 "hands) mode, 50 / 50, with a random azimuth orientation that also turns its "
                 "array; a cluster whose centre arrival direction falls in the mode's region of "
                 "Table 7.6.4.1-1 loses 30 dB, as does the LOS ray; the loss applies to the RSRP "
                 "(cell association) and to the channel")


def _grip(summ: dict) -> bool:
    return summ.get("setup") in GRIP_SETUPS


def _common(summ: dict) -> dict:
    """Assumption texts shared by the three columns, keyed by the start of the
    row label ('|<block>' = only in that block's rows)."""
    grip = _grip(summ)
    md = "cw2lm_ftp1_grip_20mhz.md" if grip else "cw2lm_ftp1_warmfast_20mhz.md"
    return {
        "Source Tdoc": f"No Tdoc: nrsls system-level simulator (HelloSYQ/NR_DL_SLS, "
                       f"results/{md})",
        "Network layout": "Hexagonal grid, 19 sites x 3 sectors (57 cells), ISD 200 m, "
                          "wrap-around",
        "Scenario": "Dense Urban-eMBB, ITU-R M.2412 configuration A; TR 38.901 UMa channel; "
                    "80 % indoor (20 % high-loss / 80 % low-loss O2I), 20 % outdoor in cars",
        "Carrier, SCS and bandwidth": summ.get("carrier", ""),
        "UE speed": "3 km/h indoor, 30 km/h in car",
        "NW antenna configuration": "32T: (M, N, P, Mg, Ng; Mp, Np) = (8, 8, 2, 1, 1; 2, 8), "
                                    "0.5 lambda spacing, 8 dBi element, BS height 25 m",
        "UE antenna configuration": "4R: (M, N, P) = (1, 2, 2)",
        "UE noise figure": "7 dB",
        "UE blockage": GRIP_BLOCKAGE if grip else "Not modelled",
        "gNB transmit power": summ.get("power", ""),
        "DL precoding method": "Reciprocity based (ideal SVD), SU-MIMO, rank <= 4: sub-band "
                               "SVD in the 'Reciprocity based precoding' rows, wideband SVD in "
                               "the 'Other precoding scheme' rows; codebook based precoding not "
                               "evaluated",
        "CSI-RS periodicity": "20 ms (RI and CQI reports)",
        "CSI feedback delay": "4 ms",
        "CSI-RS channel estimation": "Ideal",
        "Number of CSI-RS ports": "32",
        "Precoding algorithm|Codebook based precoding": "Not evaluated",
        "SRS periodicity": "20 ms (the precoder is 4 ms old when used)",
        "SRS configuration": "All 4 UE ports sounded (antenna switching assumed), full band",
        "SRS channel estimation": "Ideal",
        "IPN acquisition assumption": "Ideal: precoder from the UE's whitened channel "
                                      "(interference covariance known); RI and per-codeword "
                                      "CQI reported by the UE",
        "Precoding algorithm|Reciprocity based precoding":
            "Unquantised SVD: per 4-PRB sub-band (dominant right singular vectors) in the "
            "'Reciprocity based precoding' rows; one wideband precoder in the 'Other "
            "precoding scheme' rows",
        "MCS table": "256QAM (TS 38.214 Table 5.1.3.1-2)",
        "SU-MIMO or MU-MIMO": "SU-MIMO",
        "PDSCH resource allocation / DMRS configuration":
            "PF scheduling per 4-PRB RBG, buffer-aware; 2 PDCCH symbols, 12 PDSCH symbols; "
            "DM-RS type 1, 1 front-loaded + 1 additional symbol (24 RE/PRB); 9 RE/PRB other "
            "overhead",
        "PDSCH DMRS channel estimation": "Ideal",
        "Traffic model": "FTP model 1: 0.5 Mbyte files; users arrive at random positions as a "
                         "Poisson process per cell, download one file and leave; arrival rates "
                         "set so that NR with MMSE-IRC has 20 / 50 / 70 % RU in each precoding "
                         "case" + (", with the UE blockage" if grip else ""),
    }


def _per_column(summ: dict) -> dict:
    """{row label start: {column: text}} for the rows that differ per column."""
    conf = {(e["case"], e["load"]): e for e in summ["configurations"]}
    ms = summ.get("slot_ms", 1.0)

    def nr(case, load, key):
        e = conf.get((case, load))
        s = e and e["variants"].get(NR_VARIANT, {}).get("nr")
        return s[key] if s else None

    active = "/".join(f"{nr('svd_sb_20ms', ld, 'mean_active_ues'):.1f}" for ld in LOAD_ORDER)
    ru = {c: "/".join(f"{100 * nr(c, ld, 'ru'):.0f}" for ld in LOAD_ORDER)
          for c in ("svd_sb_20ms", "svd_20ms")}
    def drain(e):
        d = e.get("summary_drain")
        return d.get(str(e["n_slots"])) if isinstance(d, dict) else d

    by_len = {}                          # (slots, drain) -> loads run with them
    for e in summ["configurations"]:
        if e["load"] in LOAD_ORDER:
            loads = by_len.setdefault((e["n_slots"], drain(e) or 0), set())
            loads.add(e["load"])
    drops = sorted({d for e in summ["configurations"] for v in e["variants"].values()
                    for s in v.values() for d in s["drops"]})
    span = "; ".join(
        " and ".join(sorted(loads, key=int)) + f" % RU: {n:,} slots ({n * ms:,g} ms), files "
        f"arriving in the last {dr:,} slots served but not counted"
        for (n, dr), loads in sorted(by_len.items()))
    la = ("CQI per codeword (MIESM) with OLLA per UE and codeword (10 % BLER target, 0.5 dB "
          "step{sic}); warm start: a new user's loops start at the mean offset of the loops "
          "with at least 20 ACK/NACKs; fast start: x4 steps for a loop's first 20 ACK/NACKs; "
          "NR the same; up to 4 transmissions, chase combining, 8-slot ({rtt:g} ms) RTT; HARQ per "
          "codeword: failed codewords resent, decoded ones refilled with new TBs only when the "
          "current report has the same rank and the user has data left, else the failed "
          "codewords are resent alone on fewer layers; retransmissions re-precoded with the "
          "latest report")
    rank = ("UE-selected RI <= 4 maximising the sum over codewords of layers x SE(wideband "
            "CQI), knowing the codeword split{x}")
    base = (f"MIESM link abstraction. {len(drops)} drops; {span}; runs start empty (no "
            "warm-up); files still open at the end count with an upper-bound UPT. Measured NR "
            f"RU [%] at the three loads: sub-band SVD {ru['svd_sb_20ms']}, wideband SVD "
            f"{ru['svd_20ms']}; every scheme runs with the same arrivals. Alt1 with the same "
            "modulation order is the NR baseline (0 %): NR with MMSE-IRC and the same OLLA. "
            "Alt1 with a different modulation order per layer, Type I and Type II codebook "
            "not evaluated.")
    if _grip(summ):
        base += (" The same evaluation without the UE blockage is in "
                 "6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx.")
    alts = ("Alt2 = LTE split {1}/{1,1}/{1,2}/{2,2} (TS 36.211 Table 6.3.3.2-1); Alt3 = one "
            "codeword per layer. ")
    twisted = ("Alt2 rows = twisted LTE: the LTE split for rank 1-3; at rank 4, codeword 0 on "
               "layer 0 (the strongest) and codeword 1 on layers 1-3. Alt3 rows: see the "
               "MMSE-IRC column. ")
    return {
        "UEs per cell": {c: f"FTP model 1: a pool of 20 user positions per cell; on average "
                            f"{active} active users per cell at the three loads"
                         for c in COLS},
        "UE receiver": {
            "D": "MMSE-IRC",
            "E": "Codeword-level MMSE-SIC: codewords decoded in index order, decoded codewords "
                 "cancelled ideally, a failed codeword is not cancelled (error propagation); "
                 "CQI and RI computed for SIC. One codeword: MMSE-IRC",
            "F": "MMSE-IRC"},
        "Link adaptation and HARQ assumption": {
            c: la.format(sic=", counting every NACK including SIC error propagation"
                         if c == "E" else "", rtt=8 * ms) for c in COLS},
        "Rank adaptation assumption": {
            "D": rank.format(x=""), "E": rank.format(x=" and SIC"),
            "F": rank.format(x=" (twisted at rank 4)")},
        "Additional remarks": {"D": alts + base, "E": alts + base, "F": twisted + base},
    }


def plan(summ: dict, path: str, cols=tuple(COLS)) -> dict:
    """{cell reference: value} to write in the columns ``cols``: str for
    text, float for a gain (a fraction, written with a 0.0 % format), None for
    an empty cell.  Other columns are left as they are."""
    ws = openpyxl.load_workbook(path)[SHEET]
    conf = {(e["case"], e["load"]): e for e in summ["configurations"]}
    common, per_col = _common(summ), _per_column(summ)
    tag = ", with hand grip" if _grip(summ) else ""
    cells = {f"{col}2": COLS[col][0] + tag for col in cols}
    a_label = b_label = block = None
    for r in range(3, ws.max_row + 1):
        a, b, c = (_text(ws.cell(r, i).value) for i in (1, 2, 3))
        if not (a or b or c):
            continue
        a_label = a or a_label
        b_label = b or b_label
        if not b and a in BLOCKS:                          # a results block opens
            block = a
            for col in cols:
                cells[f"{col}{r}"] = None
            continue
        if block is None:                                  # assumption rows
            label = b_label if b else a_label
            text = next((v for k, v in per_col.items() if label.startswith(k)), None)
            if text is None:
                hit = next((v for k, v in common.items()
                            if label.startswith(k.partition("|")[0])
                            and (not k.partition("|")[2] or k.partition("|")[2] == a_label)),
                           None)
                text = {col: hit for col in COLS} if hit is not None else {}
            for col in cols:
                cells[f"{col}{r}"] = text.get(col)
            continue
        metric = next((m for t, m in METRICS.items() if a_label.startswith(t)), None)
        alt = next((s for t, s in ALTS.items() if b_label.startswith(t)), "?")
        load = LOADS.get(c.replace(" ", ""))
        e = conf.get((BLOCKS[block], load)) if BLOCKS.get(block) else None
        for col in cols:
            _, variant, schemes = COLS[col]
            scheme = schemes.get(alt) if alt else None
            value = None
            if e is not None and metric and scheme == "nr":
                value = 0.0
            elif e is not None and metric and scheme:
                g = e["variants"].get(variant, {}).get(scheme, {}).get("gain_vs_nr_pct")
                if g and g.get("drops"):
                    value = round(g[metric] / 100, 6)
            cells[f"{col}{r}"] = value
    return cells


def check(summ: dict, cols=tuple(COLS)) -> None:
    """Every NR reference the columns ``cols`` need is in the summary, and
    each gain is taken against NR_VARIANT on all of the drops."""
    for e in summ["configurations"]:
        if e["case"] not in BLOCKS.values() or e["load"] not in LOAD_ORDER:
            continue
        nr = e["variants"].get(NR_VARIANT, {}).get("nr")
        if nr is None:
            raise ValueError(f"no {NR_VARIANT} NR run for {e['case']} {e['load']} %")
        for col in cols:
            _, variant, schemes = COLS[col]
            for scheme in (s for s in schemes.values() if s and s != "nr"):
                st = e["variants"].get(variant, {}).get(scheme)
                if st is None:
                    raise ValueError(f"column {col}: no {variant}/{scheme} for "
                                     f"{e['case']} {e['load']} %")
                if st.get("nr_reference") != NR_VARIANT or \
                        st["gain_vs_nr_pct"]["drops"] != nr["drops"]:
                    raise ValueError(f"column {col}: {variant}/{scheme} {e['case']} "
                                     f"{e['load']} % not against {NR_VARIANT} on all drops")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", nargs="?",
                    default=os.path.join(ROOT, "results", "cw2lm_ftp1_warmfast_20mhz.json"))
    ap.add_argument("workbook", nargs="?",
                    default=os.path.join(ROOT, "6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx"))
    ap.add_argument("--columns", default=",".join(COLS),
                    help="comma-separated columns to fill, of " + ",".join(COLS))
    args = ap.parse_args()
    cols = tuple(args.columns.split(","))
    if not cols or any(c not in COLS for c in cols):
        ap.error(f"--columns: choose from {','.join(COLS)}")
    with open(args.summary) as fh:
        summ = json.load(fh)
    check(summ, cols)
    write_cells(args.workbook, plan(summ, args.workbook, cols))
    print("filled", os.path.normpath(args.workbook), "columns", ",".join(cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
