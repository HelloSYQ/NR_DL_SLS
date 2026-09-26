#!/usr/bin/env python3
"""Extract the calibration CDFs of TR 37.910 Annex A (Figures A.1-A.5).

The figures in the ETSI PDF (TR 137 910 V19.0.0, docs/tr_137910v190000p.pdf)
are vector drawings, so the curves are read from the drawing paths rather
than digitised from pixels:

  * a panel is a white chart area; its axes are calibrated by a straight-line
    fit of the tick-label centres to their values;
  * every curve is a thin filled outline (dashed curves: one outline per
    dash).  Its points are mapped to (dB, CDF) and averaged per 0.5 % CDF bin,
    which puts the curve on the centre line of the stroke;
  * curves are named from the legend by matching (colour, solid/dashed) of
    the legend sample.

Coupling gain here has the same sign as in nrsls (negative dB), so the
curves are written unchanged.  Output: refs/tr37910/<fig>_<metric>_<label>.csv
with columns ``x_db, cdf`` (cdf in 0..1) and an index.json.

    python examples/extract_tr37910_annexA.py [--pdf PATH] [--out DIR] [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import re

import numpy as np
import pymupdf

PAGES = (129, 130, 131)            # 0-based pages of Annex A (printed 129-131)


def _num(t):
    t = t.strip().replace(",", ".")
    return float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else None


def _lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t:
                out.append((pymupdf.Rect(ln["bbox"]), t))
    return out


def _subpaths(items):
    n, last = 0, None
    for it in items:
        if it[0] == "re":
            n, last = n + 1, None
            continue
        if last is None or abs(it[1].x - last.x) > 0.01 or abs(it[1].y - last.y) > 0.01:
            n += 1
        last = it[-1]
    return n


def _polygons(items, n_bezier=12):
    """Flatten a filled path into closed polylines (one per sub-path)."""
    polys, cur, last = [], [], None
    t = np.linspace(0, 1, n_bezier)[1:]
    for it in items:
        if it[0] not in ("l", "c"):
            continue
        p0 = np.array([it[1].x, it[1].y])
        if last is None or np.hypot(*(p0 - last)) > 0.01:
            if len(cur) > 2:
                polys.append(np.array(cur))
            cur = [p0]
        if it[0] == "l":
            cur.append([it[2].x, it[2].y])
        else:
            b = np.array([[q.x, q.y] for q in it[1:5]])
            cur += list(((1 - t) ** 3)[:, None] * b[0] + (3 * (1 - t) ** 2 * t)[:, None] * b[1]
                        + (3 * (1 - t) * t ** 2)[:, None] * b[2] + (t ** 3)[:, None] * b[3])
        last = np.array(cur[-1])
    if len(cur) > 2:
        polys.append(np.array(cur))
    return polys


def _crossings(polys, axis, level):
    """Coordinates where the outline crosses the line coord[axis] = level."""
    out = []
    for P in polys:
        a, b = P, np.roll(P, -1, axis=0)
        u, v = a[:, axis], b[:, axis]
        m = (u - level) * (v - level) < 0
        if m.any():
            w = (level - u[m]) / (v[m] - u[m])
            out.append(a[m, 1 - axis] + w * (b[m, 1 - axis] - a[m, 1 - axis]))
    return np.concatenate(out) if out else np.empty(0)


def _centre_line(polys, step=0.2, slack=1.6):
    """Centre line of a thin stroke outline, in page coordinates.

    Horizontal scanlines resolve the steep part of a CDF, vertical ones the
    flat tails.  A scanline cuts a stroke of width w over w / sin(angle), so
    it is used only where its crossing extent stays within ``slack`` times
    the stroke width (estimated as the 10th percentile of all extents);
    together the two directions cover every slope.
    """
    pts = np.vstack(polys)
    cand = []
    for axis in (1, 0):                      # 1: horizontal lines (y = level)
        lo, hi = pts[:, axis].min(), pts[:, axis].max()
        for level in np.arange(lo + step / 2, hi, step):
            c = _crossings(polys, axis, level)
            if len(c) >= 2:
                mid = 0.5 * (c.min() + c.max())
                cand.append((np.ptp(c), *((mid, level) if axis == 1
                                          else (level, mid))))
    if not cand:
        return np.empty((0, 2))
    cand = np.array(cand)
    width = np.percentile(cand[:, 0], 10)
    return cand[cand[:, 0] <= slack * width, 1:]


def _is_color(fill):
    return fill is not None and not (max(fill) - min(fill) < 0.05)   # not grey


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def extract(pdf_path):
    doc = pymupdf.open(pdf_path)
    curves = []
    for pno in PAGES:
        page = doc[pno]
        draws = page.get_drawings()
        lines = _lines(page)
        captions = [(r, t) for r, t in lines if t.startswith("Figure A.")]
        white = [g for g in draws if g.get("fill") == (1.0, 1.0, 1.0)
                 and len(g["items"]) == 1 and g["items"][0][0] == "re"]
        panels = [g["rect"] for g in white if g["rect"].width > 150]
        legends = [g["rect"] for g in white if g["rect"].width <= 150]
        for pr in panels:
            inside = [(r, t) for r, t in lines if pr.contains(r)]
            metric = ("coupling_gain" if any("Coupling gain" in t for _, t in inside)
                      else "geometry")
            # axis calibration from tick labels
            nums = [(r, _num(t)) for r, t in inside if _num(t) is not None]
            ymax_label = max(r.y1 for r, v in nums)
            xt = [(r, v) for r, v in nums if r.y1 > ymax_label - 3]
            yt = [(r, v) for r, v in nums if r.y1 <= ymax_label - 3
                  and r.x1 < pr.x0 + 0.2 * pr.width]
            ax = np.polyfit([(r.x0 + r.x1) / 2 for r, _ in xt], [v for _, v in xt], 1)
            ay = np.polyfit([(r.y0 + r.y1) / 2 for r, _ in yt], [v for _, v in yt], 1)
            x_res = np.abs(np.polyval(ax, [(r.x0 + r.x1) / 2 for r, _ in xt])
                           - [v for _, v in xt]).max()
            # legend entries: sample (colour, dashed) -> label text
            leg = [lr for lr in legends if pr.contains(lr)]
            entries = []
            if leg:
                lr = leg[0]
                samples = sorted([g for g in draws if _is_color(g.get("fill"))
                                  and lr.contains(g["rect"])],
                                 key=lambda g: g["rect"].y0)
                box = lr + (-2, -3, 2, 3)
                texts = [(r, t) for r, t in inside if box.contains(r)]
                ys = [s["rect"].y0 for s in samples] + [lr.y1 + 10]
                for k, s in enumerate(samples):
                    lab = " ".join(t for r, t in texts
                                   if ys[k] - 4 <= r.y0 < ys[k + 1] - 4)
                    entries.append((tuple(round(c, 3) for c in s["fill"]),
                                    _subpaths(s["items"]) > 1, lab))
            # curves
            for gi, g in enumerate(draws):
                if not _is_color(g.get("fill")) or not pr.contains(g["rect"]):
                    continue
                if any(lr.contains(g["rect"]) for lr in leg) or g["rect"].height < 30:
                    continue
                key = (tuple(round(c, 3) for c in g["fill"]), _subpaths(g["items"]) > 1)
                names = [lab for c, dsh, lab in entries if (c, dsh) == key[:2]]
                if names:
                    label = names[0]
                elif (entries and not key[1]
                      and any(c == key[0] and dsh for c, dsh, _ in entries)):
                    # a solid twin of a dashed legend entry that the legend
                    # omits (Figure A.1: Config. C, 36 TRxP)
                    twin = [lab for c, dsh, lab in entries if c == key[0] and dsh][0]
                    label = twin.replace("12TRxP", "36TRxP") + " [not in legend]"
                else:
                    # e.g. Figure A.3, drawing 47: a path that matches no legend
                    # entry and is not visible in the rendered figure
                    print(f"skipped unlabelled path: page {pno + 1}, "
                          f"drawing {gi}, rgb{key[0]}")
                    continue
                cl = _centre_line(_polygons(g["items"]))
                if len(cl) < 10:
                    continue
                xv = np.polyval(ax, cl[:, 0])
                cv = np.polyval(ay, cl[:, 1]) / 100.0
                if np.ptp(cv) < 0.5 or np.ptp(xv) < 3.0:   # not a CDF curve
                    continue
                o = np.lexsort((cv, xv))
                xc = xv[o]
                fc = np.clip(np.maximum.accumulate(cv[o]), 0.0, 1.0)
                cap = min((c for c in captions if c[0].y0 > pr.y1 - 5),
                          key=lambda c: c[0].y0 - pr.y1, default=None)
                if cap is None:
                    cap = min(captions, key=lambda c: abs(c[0].y0 - pr.y1))
                fig = cap[1].split()[1]
                curves.append(dict(figure=fig, caption=cap[1], metric=metric,
                                   label=label, dashed=key[1], rgb=key[0],
                                   page=pno + 1, drawing=gi, axis_fit_residual_db=float(x_res),
                                   x_db=xc, cdf=fc))
    return curves


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=os.path.join(here, "..", "docs",
                                                  "tr_137910v190000p.pdf"))
    ap.add_argument("--out", default=os.path.join(here, "..", "refs", "tr37910"))
    ap.add_argument("--check", action="store_true",
                    help="re-plot the extracted curves to <out>/check_*.png")
    args = ap.parse_args()
    curves = extract(args.pdf)
    os.makedirs(args.out, exist_ok=True)
    index = []
    for c in curves:
        name = f"{c['figure'].replace('.', '')}_{c['metric']}_{_slug(c['label'])}.csv"
        with open(os.path.join(args.out, name), "w") as f:
            f.write(f"# TR 37.910 V19.0.0 Annex A, {c['caption']}\n")
            f.write(f"# curve: {c['label']} ({'dashed' if c['dashed'] else 'solid'})\n")
            f.write("# extracted from the PDF vector paths; x_db, cdf\n")
            for x, p in zip(c["x_db"], c["cdf"]):
                f.write(f"{x:.3f},{p:.4f}\n")
        index.append({k: c[k] for k in ("figure", "caption", "metric", "label", "dashed",
                                          "page", "drawing", "axis_fit_residual_db")}
                     | {"file": name,
                        "p5": float(np.interp(0.05, c["cdf"], c["x_db"])),
                        "p50": float(np.interp(0.50, c["cdf"], c["x_db"])),
                        "p95": float(np.interp(0.95, c["cdf"], c["x_db"]))})
        print(f"{name:95s} p5 {index[-1]['p5']:7.1f} p50 {index[-1]['p50']:7.1f} "
              f"p95 {index[-1]['p95']:7.1f}")
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
    if args.check:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for fig in sorted({c["figure"] for c in curves}):
            fg, axs = plt.subplots(1, 2, figsize=(12, 4.5))
            for a, metric in zip(axs, ("coupling_gain", "geometry")):
                for c in curves:
                    if c["figure"] == fig and c["metric"] == metric:
                        a.plot(c["x_db"], 100 * c["cdf"], ls="--" if c["dashed"] else "-",
                               color=c["rgb"], label=c["label"])
                a.set_xlabel(metric)
                a.grid(alpha=0.3)
                a.legend(fontsize=6)
            fg.suptitle(f"re-plot of Figure {fig}")
            fg.tight_layout()
            fg.savefig(os.path.join(args.out, f"check_{fig.replace('.', '')}.png"), dpi=90)
            plt.close(fg)


if __name__ == "__main__":
    main()
