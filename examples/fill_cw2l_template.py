#!/usr/bin/env python3
"""Fill the 'SLS rank 1-4' sheet of the 6GR CW2L result-collection template
with the FTP evaluation (examples/cw2lm_ftp_eval.py).

Two columns: D = MMSE-IRC receiver, E = codeword-level MMSE-SIC receiver,
both with OLLA per codeword.  Results go to the 'Type II codebook' block
(eType-II) and the 'Reciprocity based precoding' block (sub-band SVD); the
Type I and 'Other precoding scheme' blocks and the rows for Alt1 with a
different modulation order per layer stay empty (not evaluated).  Alt1 with
the same modulation order is the NR mapping, the baseline (0 %).  Gains are
written as fractions with a 0.0 % format.  Rows are found by their labels
(read with openpyxl); the values are written by patching the sheet's XML, so
the rest of the workbook is left exactly as it was.

    python examples/fill_cw2l_template.py [results/cw2lm_ftp.json] \\
        [6GR_DL_CW2L_template_v003.xlsx]
"""

from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

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


def _assumption(label: str, parent: str, traffic: str, remarks: str, common: dict = COMMON,
                per_col: dict = PER_COL) -> dict:
    """{column key: text} of an assumption row, matched on the start of its
    label ('Precoding algorithm' also on the block it belongs to)."""
    for key, v in common.items():
        name, _, blk = key.partition("|")
        if label.startswith(name) and (not blk or blk == parent):
            return {k: v for k in COLS}
    for key, v in per_col.items():
        if label.startswith(key):
            return v
    if label.startswith("Traffic model"):
        return {k: traffic for k in COLS}
    if label.startswith("Additional remarks"):
        return {k: remarks for k in COLS}
    return {}


def _text(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def plan(summ: dict, path: str) -> dict:
    """{cell reference: value} to write: str for text, float for a gain
    (written as a fraction with a 0.0 % format).  Rows are found by their labels."""
    ws = openpyxl.load_workbook(path)[SHEET]
    conf = {(e["case"], e["load"]): e for e in summ["configurations"]}
    # set-up of the summary (carrier, power, slot length); older summaries are 10 MHz
    ms = summ.get("slot_ms", 1.0)
    common = dict(COMMON)
    common["Carrier, SCS and bandwidth"] = summ.get("carrier", COMMON["Carrier, SCS and bandwidth"])
    common["gNB transmit power"] = summ.get("power", COMMON["gNB transmit power"])
    per_col = {k: {c: (t.replace("8-slot RTT", f"8-slot ({8 * ms:g} ms) RTT") if ms != 1 else t)
                   for c, t in v.items()} for k, v in PER_COL.items()}

    # measured RU of NR per case and load, for the remarks
    def nr_ru(c, ld):
        s = conf.get((c, ld), {}).get("variants", {}).get("irc-olla", {}).get("nr")
        return f"{100 * s['ru']:.0f}" if s else "n/a"
    ru = {c: "/".join(nr_ru(c, ld) for ld in ("20", "50", "70")) for c in BLOCKS.values()}
    drops = sorted({d for e in summ["configurations"]
                    for v in e["variants"].values() for s in v.values() for d in s["drops"]})
    e0 = summ["configurations"][0]
    remarks = (
        "MIESM link abstraction. Alt2 = LTE split {1}/{1,1}/{1,2}/{2,2} (TS 36.211 Table "
        "6.3.3.2-1); Alt3 = one codeword per layer. Alt1 with the same modulation order is "
        "the NR baseline (0 %); Alt1 with a different modulation order per layer, Type I and "
        f"other precoding not evaluated. {len(drops)} drops of {e0['n_slots'] * ms:g} ms "
        f"({e0['warmup'] * ms:g} ms warm-up; files arriving in the last {e0['drain'] * ms:g} ms are "
        "served but not counted; files still open at the end count with an upper-bound "
        f"UPT). Measured NR RU [%] at the three loads: eType-II {ru['etype2_20ms']}, "
        f"sub-band SVD {ru['svd_sb_20ms']}; every scheme runs with the same files.")
    traffic = ("FTP model 3: 0.5 Mbyte files, Poisson arrivals per UE; arrival rates set so "
               "that NR with MMSE-IRC has 20 / 50 / 70 % RU in each precoding case")

    cells = {f"{col}2": {"irc-olla": "nrsls, MMSE-IRC", "sic-olla": "nrsls, CW-level SIC"}[k]
             for k, col in COLS.items()}
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
            vals = _assumption(b_label if b else a_label, a_label, traffic, remarks, common, per_col)
            for k, v in vals.items():
                cells[f"{COLS[k]}{r}"] = v
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
            if alt == "nr":
                cells[f"{col}{r}"] = 0.0
            elif e and alt in e["variants"].get(k, {}):
                g = e["variants"][k][alt].get("gain_vs_nr_pct")
                if g:
                    cells[f"{col}{r}"] = round(g[metric] / 100, 6)
    return cells


# --- writing: patch the sheet XML in place ------------------------------------
# openpyxl would rewrite the whole package: it expands row styles into tens of
# thousands of cells and drops parts it does not know (custom XML, sensitivity
# label metadata, printer settings).  So only the sheet's XML and styles.xml are
# changed here, and every other part of the package is copied as it is.

def _colnum(letters: str) -> int:
    n = 0
    for ch in letters:
        n = 26 * n + ord(ch) - 64
    return n


def _split_ref(ref: str) -> tuple:
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return m.group(1), int(m.group(2))


def _attr(tag: str, name: str):
    m = re.search(rf'\s{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def _set_attr(tag: str, name: str, value: str) -> str:
    if _attr(tag, name) is not None:
        return re.sub(rf'(\s{name}=")[^"]*(")', rf"\g<1>{value}\g<2>", tag, count=1)
    return re.sub(r"\s*(/?>)$", rf' {name}="{value}"\1', tag, count=1)


def _sheet_part(z: zipfile.ZipFile, sheet: str) -> str:
    wb = z.read("xl/workbook.xml").decode()
    tag = next(t for t in re.findall(r"<sheet\s[^>]*>", wb)
               if _attr(t, "name") == escape(sheet, {'"': "&quot;"}))
    rid = re.search(r'\sr:id="([^"]+)"', tag).group(1)
    rels = z.read("xl/_rels/workbook.xml.rels").decode()
    rel = next(t for t in re.findall(r"<Relationship\s[^>]*>", rels) if _attr(t, "Id") == rid)
    target = _attr(rel, "Target")
    return target.lstrip("/") if target.startswith("/") else "xl/" + target


class _Styles:
    """Adds, per existing cell style, a copy with the 0.0 % number format."""

    def __init__(self, xml: str):
        self.xml, self.pct = xml, {}
        ids = [int(i) for i in re.findall(r'<numFmt\s[^>]*numFmtId="(\d+)"', xml)]
        found = re.search(r'<numFmt\s[^>]*numFmtId="(\d+)"[^>]*formatCode="0\.0%"', xml)
        if found:
            self.fmt = int(found.group(1))
        else:
            self.fmt = max(ids + [163]) + 1
            nf = f'<numFmt numFmtId="{self.fmt}" formatCode="0.0%"/>'
            if re.search(r"<numFmts\b[^>]*/>", xml):          # empty: <numFmts count="0"/>
                self.xml = re.sub(r"<numFmts\b[^>]*/>", f'<numFmts count="1">{nf}</numFmts>',
                                  self.xml, count=1)
            elif "<numFmts" in xml:
                self.xml = re.sub(r"</numFmts>", nf + "</numFmts>", self.xml, count=1)
                self.xml = re.sub(r'(<numFmts\s+count=")(\d+)',
                                  lambda m: m.group(1) + str(int(m.group(2)) + 1), self.xml, 1)
            else:                               # numFmts is the first child of styleSheet
                self.xml = re.sub(r"(<styleSheet\b[^>]*>)", rf'\1<numFmts count="1">{nf}</numFmts>',
                                  self.xml, count=1)

    def percent(self, s: int) -> int:
        if s in self.pct.values():              # already one of the added 0.0 % styles
            return s
        if s not in self.pct:
            m = re.search(r'<cellXfs\s+count="(\d+)"\s*>(.*?)</cellXfs>', self.xml, re.S)
            xfs = re.findall(r"<xf\b[^>]*/>|<xf\b[^>]*>.*?</xf>", m.group(2), re.S)
            head = re.match(r"<xf\b[^>]*?/?>", xfs[s]).group(0)
            new_head = _set_attr(_set_attr(head, "numFmtId", str(self.fmt)),
                                 "applyNumberFormat", "1")
            xf = new_head + xfs[s][len(head):]
            body = m.group(2) + xf
            self.xml = (self.xml[:m.start()] + f'<cellXfs count="{len(xfs) + 1}">' + body
                        + "</cellXfs>" + self.xml[m.end():])
            self.pct[s] = len(xfs)
        return self.pct[s]


def _patch_sheet(xml: str, cells: dict, styles: _Styles) -> str:
    by_row = {}
    for ref, v in cells.items():
        col, row = _split_ref(ref)
        by_row.setdefault(row, []).append((_colnum(col), ref, v))
    max_col = 0
    for row, items in sorted(by_row.items()):
        m = re.search(rf'<row\s+r="{row}"(?=[\s>/])[^>]*?(?:/>|>(.*?)</row>)', xml, re.S)
        if m is None:
            raise ValueError(f"row {row} not in the sheet")
        open_tag = re.match(r"<row\b[^>]*?/?>", m.group(0)).group(0)
        content = m.group(1) or ""
        for cn, ref, v in sorted(items):
            max_col = max(max_col, cn)
            cm = re.search(rf'<c\s+r="{ref}"(?=[\s>/])[^>]*?(?:/>|>.*?</c>)', content, re.S)
            if cm:
                s = _attr(re.match(r"<c\b[^>]*?/?>", cm.group(0)).group(0), "s")
            else:                    # new cell: style of the nearest cell to its left
                left = [c for c in re.findall(r"<c\b[^>]*?/?>", content)
                        if _colnum(_split_ref(_attr(c, "r"))[0]) < cn]
                s = _attr(left[-1], "s") if left else _attr(open_tag, "s")
            if v is None:            # an empty cell that keeps (or takes) the style
                sa = f' s="{s}"' if s is not None else ""
                new = f'<c r="{ref}"{sa}/>'
            elif isinstance(v, str):
                sa = f' s="{s}"' if s is not None else ""
                text = escape(v)
                new = (f'<c r="{ref}"{sa} t="inlineStr"><is><t xml:space="preserve">{text}'
                       f"</t></is></c>")
            else:
                new = f'<c r="{ref}" s="{styles.percent(int(s or 0))}"><v>{float(v)!r}</v></c>'
            if cm:
                content = content[:cm.start()] + new + content[cm.end():]
            else:
                after = [c for c in re.finditer(r'<c\s+r="([A-Z]+)\d+"', content)
                         if _colnum(c.group(1)) > cn]
                pos = after[0].start() if after else len(content)
                content = content[:pos] + new + content[pos:]
        tag = open_tag.rstrip("/>").rstrip() + ">" if open_tag.endswith("/>") else open_tag
        spans = _attr(tag, "spans")
        if spans and ":" in spans:
            lo, hi = (int(x) for x in spans.split(":"))
            tag = _set_attr(tag, "spans", f"{min(lo, min(i[0] for i in items))}:"
                                          f"{max(hi, max(i[0] for i in items))}")
        xml = xml[:m.start()] + tag + content + "</row>" + xml[m.end():]
    dm = re.search(r'<dimension\s+ref="([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?"', xml)
    if dm and dm.group(3) and _colnum(dm.group(3)) < max_col:
        letters, n = "", max_col
        while n:
            n, r = divmod(n - 1, 26)
            letters = chr(65 + r) + letters
        xml = xml[:dm.start(3)] + letters + xml[dm.end(3):]
    return xml


def write_cells(path: str, cells: dict, sheet: str = SHEET) -> None:
    """Write ``cells`` into ``sheet`` of the workbook at ``path`` in place,
    changing only that sheet's XML and the styles."""
    with zipfile.ZipFile(path) as z:
        part = _sheet_part(z, sheet)
        styles = _Styles(z.read("xl/styles.xml").decode())
        sheet_xml = _patch_sheet(z.read(part).decode(), cells, styles)
        entries = [(i, z.read(i.filename)) for i in z.infolist()]
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as out:
        for info, data in entries:
            if info.filename == part:
                data = sheet_xml.encode()
            elif info.filename == "xl/styles.xml":
                data = styles.xml.encode()
            out.writestr(info, data, compress_type=info.compress_type)
    os.replace(tmp, path)


def fill(summ: dict, path: str) -> None:
    write_cells(path, plan(summ, path))


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
