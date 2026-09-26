#!/usr/bin/env python3
"""Import the per-company calibration CDFs attached to RP-180524.

``docs/Calibration results for IMT-2020 submission.zip`` holds one workbook
per ITU-R M.2412 test environment and one sheet per evaluation configuration
(e.g. ``Rural_700M_ModelA``).  Each sheet lists, for every company, the
coupling gain and the DL geometry at the 0, 1, ..., 100 % points of the CDF
(rows 29-129; companies in row 25; coupling gain in columns B.., geometry
from column AG; a 'Mean' column closes each block).  These are the data
behind TR 37.910 Figures A.1-A.5.

Writes refs/rp180524/<sheet>_<metric>.csv with columns
``pct, mean, min, max, <company>...`` plus index.json.

    python examples/import_rp180524.py [--zip PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import zipfile

import numpy as np
import openpyxl

HEADER_ROW, FIRST_DATA_ROW = 24, 28          # 0-based: rows 25 and 29
METRICS = {"coupling_gain": (1, 31), "geometry": (32, 62)}   # column ranges


def read_sheet(ws):
    rows = list(ws.iter_rows(values_only=True, max_row=FIRST_DATA_ROW + 101))
    hdr = rows[HEADER_ROW]
    data = rows[FIRST_DATA_ROW:FIRST_DATA_ROW + 101]
    pct = np.array([r[0] for r in data], float)
    if not np.array_equal(pct, np.arange(101)):
        raise ValueError(f"{ws.title}: unexpected percentile column")
    out = {}
    for metric, (c0, c1) in METRICS.items():
        cols = {}
        for c in range(c0, min(c1, len(hdr))):
            name = hdr[c]
            if not isinstance(name, str) or not name.strip():
                continue
            v = np.array([r[c] if isinstance(r[c], (int, float)) else np.nan
                          for r in data], float)
            if np.isfinite(v).sum() > 90:
                cols[name.strip()] = v
        mean = cols.pop("Mean", None)
        comp = np.array(list(cols.values()))
        out[metric] = dict(pct=pct, companies=cols,
                           mean=mean if mean is not None else np.nanmean(comp, 0),
                           min=np.nanmin(comp, 0), max=np.nanmax(comp, 0))
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=os.path.join(
        here, "..", "docs", "Calibration results for IMT-2020 submission.zip"))
    ap.add_argument("--out", default=os.path.join(here, "..", "refs", "rp180524"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    index = []
    with zipfile.ZipFile(args.zip) as z:
        for name in sorted(n for n in z.namelist() if n.endswith(".xlsx")):
            wb = openpyxl.load_workbook(io.BytesIO(z.read(name)), data_only=True,
                                        read_only=True)
            for ws in wb.worksheets:
                if ws.title.lower().startswith(("revision", "assumption")):
                    continue
                for metric, d in read_sheet(ws).items():
                    fn = f"{ws.title}_{metric}.csv"
                    names = list(d["companies"])
                    table = np.column_stack([d["pct"], d["mean"], d["min"], d["max"]]
                                            + [d["companies"][n] for n in names])
                    with open(os.path.join(args.out, fn), "w") as f:
                        f.write(f"# RP-180524 attachment, {name}, sheet {ws.title}\n")
                        f.write("pct,mean,min,max," + ",".join(
                            n.replace(",", ";") for n in names) + "\n")
                        for row in table:
                            f.write(",".join("" if np.isnan(v) else f"{v:.3f}"
                                             for v in row) + "\n")
                    m = d["mean"]
                    index.append(dict(workbook=name, sheet=ws.title, metric=metric,
                                      file=fn, n_companies=len(names),
                                      p5=float(m[5]), p50=float(m[50]),
                                      p95=float(m[95])))
                    print(f"{fn:45s} {len(names):2d} companies  mean p5/50/95 "
                          f"{m[5]:7.1f} {m[50]:7.1f} {m[95]:7.1f}")
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, indent=1)


if __name__ == "__main__":
    main()
