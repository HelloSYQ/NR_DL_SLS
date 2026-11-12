#!/usr/bin/env node
// Word report of the final CW2L evaluation (FTP model 1, 20 MHz, MMSE-IRC,
// hand grip).  Numbers come from results/cw2lm_final/report_data.json
// (examples/cw2lm_final_report.py); the text is in cw2lm_final_report_text.json.
//
//     node examples/cw2lm_final_report.js [data.json] [gain.png] [out.docx]
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Footer, PageNumber,
  AlignmentType, HeadingLevel, WidthType, ShadingType, BorderStyle, LevelFormat, VerticalAlign,
} = require("docx");

const ROOT = path.join(__dirname, "..");
const dataPath = process.argv[2] || path.join(ROOT, "results", "cw2lm_final", "report_data.json");
const figPath = process.argv[3] || path.join(ROOT, "results", "cw2lm_final", "gain.png");
const outPath = process.argv[4] || path.join(ROOT, "docs", "CW2L_FTP1_hand_grip_report.docx");
const D = JSON.parse(fs.readFileSync(dataPath));
const T = JSON.parse(fs.readFileSync(path.join(__dirname, "cw2lm_final_report_text.json")));

const FONT = "Arial";
const W = 9026;                         // A4 text width with 1 inch margins, DXA
const INK = "1A1A1A", MUTED = "555555", HEAD = "E8EEF7", LINE = "BFC5CE";
const CASES = Object.keys(D.cases), LOADS = D.loads;
const fmt = (x, n = 1) => x.toFixed(n).replace("-", "−");
const sgn = (x, n = 1) => { const t = Math.abs(x).toFixed(n); return (Number(t) === 0 ? "" : x > 0 ? "+" : "−") + t; };
const G = (c, ld, s) => (D.grip[`${c}|${ld}`] || { schemes: {} }).schemes[s];
const R = (c, ld, s) => (D.ref[`${c}|${ld}`] || { schemes: {} }).schemes[s];

// --- building blocks ------------------------------------------------------
// text with **bold** spans
function runs(text, opt = {}) {
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((t) =>
    t.startsWith("**") ? new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, ...opt })
      : new TextRun({ text: t, font: FONT, ...opt }));
}
const P = (text, opt = {}) => new Paragraph({
  children: runs(text, opt.run), spacing: { after: 120, line: 276 }, ...opt.par });
const H1 = (t, brk) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: !!brk,
  children: [new TextRun({ text: t, font: FONT })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT })] });
const B = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, children: runs(text), spacing: { after: 80, line: 276 } });
const CAP = (text) => new Paragraph({
  children: runs(text, { size: 18, color: MUTED }), spacing: { before: 60, after: 200 }, keepLines: true });
const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border };

function table(head, rows, widths, opt = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const w = widths.map((x) => Math.round((x * W) / sum));
  w[w.length - 1] += W - w.reduce((a, b) => a + b, 0);
  const size = opt.size || 18;
  const cell = (text, i, isHead) => new TableCell({
    borders, width: { size: w[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    shading: isHead ? { fill: HEAD, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({
      alignment: i === 0 || (opt.left || []).includes(i) ? AlignmentType.LEFT : AlignmentType.CENTER,
      children: runs(text, { size, bold: isHead, color: INK }) })] });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: w,
    rows: [new TableRow({ tableHeader: true, cantSplit: true, children: head.map((t, i) => cell(t, i, true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, i, false)) }))] });
}
const SHORT = (c) => D.cases[c].replace(" SVD", "");
const SCH = { lte: "LTE style (Alt2)", per_layer: "1 CW per layer (Alt3)", nr: "NR (Alt1)" };

// --- tables from the data -------------------------------------------------
function headline() {
  const rows = [];
  for (const c of CASES) for (const s of ["lte", "per_layer"]) {
    rows.push([D.cases[c], SCH[s],
      ...LOADS.map((ld) => { const g = G(c, ld, s); return g ? `${sgn(g.gain_mean)} ± ${fmt(g.gain_se)} %` : "—"; }),
      LOADS.map((ld) => { const g = G(c, ld, s); return g ? `${g.drops_pos}` : "—"; }).join(" / ")]);
  }
  return table(["Precoding", "Scheme", ...LOADS.map((l) => `${l} % RU`), "Drops above zero (of 10)"],
    rows, [16, 22, 15, 15, 15, 17], { left: [1] });
}
function percentiles() {
  const rows = [];
  for (const c of CASES) for (const ld of LOADS) for (const s of ["lte", "per_layer"]) {
    const g = G(c, ld, s);
    if (g) rows.push([SHORT(c), `${ld} %`, SCH[s], `${sgn(g.gain_mean)} %`, `${sgn(g.gain_p5)} %`,
      `${sgn(g.gain_p95)} %`, `${sgn(g.drop_min)} to ${sgn(g.drop_max)} %`]);
  }
  return table(["Precoding (SVD)", "Load", "Scheme", "Mean UPT", "5th pct UPT", "95th pct UPT", "Single drops, mean UPT"],
    rows, [16, 9, 23, 12, 12, 12, 20], { left: [2] });
}
function baseline() {
  const rows = [];
  for (const c of CASES) for (const ld of LOADS) for (const s of ["nr", "lte", "per_layer"]) {
    const g = G(c, ld, s);
    if (g) rows.push([SHORT(c), `${ld} %`, SCH[s], `${fmt(g.ru, 0)} %`,
      `${fmt(g.upt_mean, 0)} / ${fmt(g.upt_p5, 0)} / ${fmt(g.upt_p95, 0)}`,
      g.bler_cw.map((x) => fmt(x, 0)).join(" / "), fmt(g.mean_rank, 2), `${fmt(g.rank_hist[3], 0)} %`,
      `${fmt(g.retx, 1)} %`]);
  }
  return table(["Precoding (SVD)", "Load", "Scheme", "RU", "UPT mean / 5th / 95th pct [Mbit/s]",
    "First-tx BLER per CW [%]", "Mean rank", "Rank-4 share", "Retx share of RBGs"],
  rows, [14, 8, 21, 7, 20, 17, 8, 9, 9], { left: [2], size: 16 });
}
function gripEffect() {
  const rows = [];
  for (const c of CASES) for (const ld of LOADS) {
    const a = R(c, ld, "nr"), b = G(c, ld, "nr");
    if (!a || !b) continue;
    const gg = (X, s) => { const g = X(c, ld, s); return g ? sgn(g.gain_mean) : "—"; };
    rows.push([SHORT(c), `${ld} %`, `${fmt(a.ru, 0)} → ${fmt(b.ru, 0)}`,
      `${fmt(a.upt_mean, 0)} → ${fmt(b.upt_mean, 0)}`, `${fmt(a.mean_rank, 2)} → ${fmt(b.mean_rank, 2)}`,
      `${fmt(a.rank_hist[3], 0)} → ${fmt(b.rank_hist[3], 0)}`,
      `${gg(R, "lte")} → ${gg(G, "lte")}`, `${gg(R, "per_layer")} → ${gg(G, "per_layer")}`]);
  }
  return table(["Precoding (SVD)", "Load", "NR: RU [%]", "NR: mean UPT [Mbit/s]", "NR: mean rank", "NR: rank-4 share [%]",
    "LTE style gain [%]", "1 CW per layer gain [%]"], rows, [13, 8, 12, 14, 14, 13, 13, 13], { size: 17 });
}
function perDrop() {
  const rows = [];
  for (const c of CASES) for (const ld of LOADS) for (const s of ["lte", "per_layer"]) {
    const g = G(c, ld, s);
    if (g) rows.push([`${D.cases[c]}, ${ld} %, ${s === "lte" ? "LTE style" : "1 CW per layer"}`,
      ...g.gain_drops.map((x) => sgn(x))]);
  }
  return table(["Precoding, load, scheme", ...[...Array(10).keys()].map((i) => `Drop ${i}`)], rows,
    [38, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7], { size: 15 });
}
function rates() {
  const r = D.cw2lm_ftp1_grip_hand_fair_rates_20mhz;
  if (!r) return P("—");
  const rows = CASES.filter((c) => r[c]).map((c) => [D.cases[c],
    ...LOADS.map((ld) => fmt(r[c].rates[ld], 2)),
    LOADS.map((ld) => { const g = G(c, ld, "nr"); return g ? fmt(g.ru, 0) : "—"; }).join(" / ") + " %"]);
  return table(["Precoding", ...LOADS.map((l) => `${l} % RU target`), "NR's RU in the evaluation runs"], rows,
    [20, 18, 18, 18, 26]);
}
const TABLES = { headline, percentiles, baseline, gripEffect, perDrop, rates };

// --- document -------------------------------------------------------------
const body = [];
for (const blk of T.blocks) {
  if (blk.h1) body.push(H1(blk.h1, blk.break));
  else if (blk.h2) body.push(H2(blk.h2));
  else if (blk.p) body.push(P(blk.p));
  else if (blk.b) blk.b.forEach((t) => body.push(B(t)));
  else if (blk.cap) body.push(CAP(blk.cap));
  else if (blk.auto) body.push(TABLES[blk.auto]());
  else if (blk.table) body.push(table(blk.table.head, blk.table.rows, blk.table.widths, blk.table.opt || {}));
  else if (blk.fig) {
    body.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(figPath),
        transformation: { width: 600, height: Math.round(600 * blk.fig.ratio) },
        altText: { title: "UPT gain", description: blk.fig.alt, name: "gain" } })] }));
  }
}

const doc = new Document({
  creator: "NR_DL_SLS", title: T.title, description: T.subtitle,
  styles: {
    default: { document: { run: { font: FONT, size: 20, color: INK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: "1F3864" },
        paragraph: { spacing: { before: 360, after: 140 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "1F3864" },
        paragraph: { spacing: { before: 260, after: 110 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 250 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 },
      margin: { top: 1440, right: 1440, bottom: 1300, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: MUTED })] })] }) },
    children: [
      new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: T.title, font: FONT, size: 40, bold: true, color: "1F3864" })] }),
      new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: T.subtitle, font: FONT, size: 22, color: MUTED })] }),
      new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "1F3864", space: 6 } },
        children: [new TextRun({ text: T.dateline, font: FONT, size: 18, color: MUTED })] }),
      ...body,
    ],
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(outPath, buf); console.log("wrote", outPath); });
