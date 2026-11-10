"""examples/fill_cw2l_template_ftp1: the FTP model 1 warm + fast results land
in the 20 MHz template copy (columns D, E and the twisted-LTE column F), the
codebook blocks are cleared, and write_cells' empty cells keep or take a style."""

import os
import shutil
import sys
import zipfile

import openpyxl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
import fill_cw2l_template_ftp1 as ftp1  # noqa: E402
from fill_cw2l_template import write_cells  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(__file__), "..",
                        "6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx")
CASES = {"svd_sb_20ms": 10, "svd_20ms": 20}
LOADS = {"20": 1, "50": 2, "70": 3}
METRICS = {"upt_mean": 0.1, "upt_p5": 0.2, "upt_p95": 0.3}
SCHEMES = {"lte": 0.01, "lte_twisted": 0.02, "per_layer": 0.03}
VARIANTS = {"irc-fix-warmfast": 0.0, "sic-fix-warmfast": 100.0}


def gain(case, load, variant, scheme, metric):
    return (CASES[case] + LOADS[load] + METRICS[metric] + SCHEMES[scheme]
            + VARIANTS[variant])


def summary(sic_reference="irc-fix-warmfast"):
    drops = list(range(10))
    confs = []
    for case in CASES:
        for load in LOADS:
            v = {"irc-fix-warmfast": {"nr": {"drops": drops, "ru": 0.2 * LOADS[load],
                                             "mean_active_ues": 0.5 * LOADS[load]}},
                 "sic-fix-warmfast": {}}
            for variant in VARIANTS:
                for scheme in SCHEMES:
                    if variant == "sic-fix-warmfast" and scheme == "lte_twisted":
                        continue
                    ref = sic_reference if variant.startswith("sic") else "irc-fix-warmfast"
                    v[variant][scheme] = {
                        "drops": drops, "nr_reference": ref,
                        "gain_vs_nr_pct": dict({m: gain(case, load, variant, scheme, m)
                                                for m in METRICS}, drops=drops)}
            confs.append({"case": case, "load": load, "n_slots": 2000 if load == "70" else 1000,
                          "summary_drain": {"1000": 300, "2000": 1000}, "variants": v})
    return {"carrier": "4 GHz FDD, 30 kHz SCS, 20 MHz channel (52 PRB)",
            "power": "44 dBm per 20 MHz", "slot_ms": 0.5, "configurations": confs}


def rows(ws):
    """{(block, metric label start, alternative label start, load): row}."""
    out, block, a_label, b_label = {}, None, None, None
    for r in range(3, ws.max_row + 1):
        a, b, c = (ftp1._text(ws.cell(r, i).value) for i in (1, 2, 3))
        a_label, b_label = a or a_label, b or b_label
        if not b and a in ftp1.BLOCKS:
            block = a
            continue
        if block and c:
            out[(block, a_label[:4], b_label[:4] + ("s" if "same" in b_label else ""),
                 c.replace(" ", ""))] = r
    return out


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "t.xlsx"
    shutil.copy(TEMPLATE, path)
    return str(path)


def test_ftp1_fill_on_the_20mhz_template(book):
    summ = summary()
    ftp1.check(summ)
    before = {i.filename: zipfile.ZipFile(book).read(i.filename)
              for i in zipfile.ZipFile(book).infolist()}
    write_cells(book, ftp1.plan(summ, book))
    z = zipfile.ZipFile(book)
    after = {i.filename: z.read(i.filename) for i in z.infolist()}
    assert list(after) == list(before)
    changed = {f for f in before if before[f] != after[f]}
    assert len(changed) == 2 and "xl/styles.xml" in changed

    wb = openpyxl.load_workbook(book)
    ws = wb[ftp1.SHEET]
    assert [ws[f"{c}2"].value for c in "DEF"] == [
        "nrsls, MMSE-IRC", "nrsls, CW-level SIC", "nrsls, MMSE-IRC, Alt2 = twisted LTE"]
    assert "FTP model 1" in ws["D30"].value and ws["D30"].value == ws["F30"].value
    assert "twisted" in ws["F33"].value and "twisted" not in ws["D33"].value
    assert "SIC" in ws["E11"].value and ws["F11"].value == "MMSE-IRC"
    r = rows(ws)
    blk = {"svd_sb_20ms": "Reciprocity based precoding", "svd_20ms": "Other precoding scheme"}
    for case, block in blk.items():
        for load in LOADS:
            for metric, label in (("upt_mean", "Mean"), ("upt_p5", "5th-"),
                                  ("upt_p95", "95th")):
                key = lambda alt: (block, label, alt, f"{load}%RU")
                nr_row, lte_row, cw_row = r[key("Alt1s")], r[key("Alt2")], r[key("Alt3")]
                assert [ws[f"{c}{nr_row}"].value for c in "DEF"] == [0, 0, 0]
                assert ws[f"D{lte_row}"].value == pytest.approx(
                    gain(case, load, "irc-fix-warmfast", "lte", metric) / 100)
                assert ws[f"E{lte_row}"].value == pytest.approx(
                    gain(case, load, "sic-fix-warmfast", "lte", metric) / 100)
                assert ws[f"F{lte_row}"].value == pytest.approx(
                    gain(case, load, "irc-fix-warmfast", "lte_twisted", metric) / 100)
                assert ws[f"D{cw_row}"].value == pytest.approx(
                    gain(case, load, "irc-fix-warmfast", "per_layer", metric) / 100)
                assert ws[f"E{cw_row}"].value == pytest.approx(
                    gain(case, load, "sic-fix-warmfast", "per_layer", metric) / 100)
                assert ws[f"F{cw_row}"].value is None
                assert ws[f"F{lte_row}"].number_format == "0.0%"
                assert ws[f"F{lte_row}"].border.left.style == ws[f"E{lte_row}"].border.left.style
                assert ws[f"D{r[key('Alt1')]}"].value is None      # different modulation
    # the codebook blocks hold nothing (the earlier eType-II values are cleared)
    for (block, *_), row in r.items():
        if block in ("Type I codebook", "Type II codebook"):
            assert all(ws[f"{c}{row}"].value is None for c in "DEF"), row
    # the other sheets are untouched
    orig = openpyxl.load_workbook(TEMPLATE)
    for name in orig.sheetnames:
        if name != ftp1.SHEET:
            assert [[c.value for c in row] for row in orig[name].iter_rows()] == \
                [[c.value for c in row] for row in wb[name].iter_rows()]


def test_ftp1_check_wants_the_irc_nr_reference_on_all_drops():
    with pytest.raises(ValueError):
        ftp1.check(summary(sic_reference="sic-fix-warmfast"))
    summ = summary()
    del summ["configurations"][0]["variants"]["irc-fix-warmfast"]["lte_twisted"]
    with pytest.raises(ValueError):
        ftp1.check(summ)


def test_write_cells_empty_cell_keeps_or_takes_the_style(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SLS rank 1-4"
    ws["D3"], ws["E3"] = 0.25, "x"
    ws["D3"].font = openpyxl.styles.Font(bold=True)
    ws["E3"].border = openpyxl.styles.Border(left=openpyxl.styles.Side(style="thin"))
    path = tmp_path / "t.xlsx"
    wb.save(path)
    write_cells(str(path), {"D3": None, "F3": None})
    ws = openpyxl.load_workbook(path)["SLS rank 1-4"]
    assert ws["D3"].value is None and ws["D3"].font.bold          # value gone, style kept
    assert ws["E3"].value == "x"
    assert ws["F3"].value is None and ws["F3"].border.left.style == "thin"   # E3's style


def _label_row(ws, start):
    return next(r for r in range(3, 40) if ftp1._text(ws.cell(r, 1).value).startswith(start))


def test_grip_summary_switches_the_blockage_texts(book, tmp_path):
    # without the grip the UE blockage row says so
    write_cells(book, ftp1.plan(summary(), book))
    ws = openpyxl.load_workbook(book)[ftp1.SHEET]
    assert ws[f"D{_label_row(ws, 'UE blockage')}"].value == "Not modelled"
    # the grip set-up fills the same cells with the grip's texts
    grip = dict(summary(), setup="20mhz-ftp1-grip")
    ftp1.check(grip)
    write_cells(book, ftp1.plan(grip, book))
    ws = openpyxl.load_workbook(book)[ftp1.SHEET]
    for col in "DEF":
        blockage = ws[f"{col}{_label_row(ws, 'UE blockage')}"].value
        assert "Self-blocking" in blockage and "7.6.4.1" in blockage and "30 dB" in blockage
        assert "cw2lm_ftp1_grip_20mhz.md" in ws[f"{col}{_label_row(ws, 'Source Tdoc')}"].value
        assert ws[f"{col}{_label_row(ws, 'Traffic model')}"].value.endswith(
            "with the UE blockage")
        assert "without the UE blockage" in ws[f"{col}{_label_row(ws, 'Additional remarks')}"].value
    # the results cells do not depend on the set-up
    r = rows(ws)
    key = ("Reciprocity based precoding", "Mean", "Alt2", "50%RU")
    assert ws[f"E{r[key]}"].value == pytest.approx(
        gain("svd_sb_20ms", "50", "sic-fix-warmfast", "lte", "upt_mean") / 100)


def test_column_subset_fills_only_those_columns(book):
    before = openpyxl.load_workbook(book)[ftp1.SHEET]
    keep = {(r, c): before.cell(r, c).value for r in range(1, before.max_row + 1) for c in (5, 6)}
    grip = dict(summary(), setup="20mhz-ftp1-grip")
    ftp1.check(grip, ("D",))
    write_cells(book, ftp1.plan(grip, book, ("D",)))
    ws = openpyxl.load_workbook(book)[ftp1.SHEET]
    assert ws["D2"].value == "nrsls, MMSE-IRC, with hand grip"
    assert all(ws.cell(r, c).value == v for (r, c), v in keep.items())   # E, F untouched
    r = rows(ws)
    key = lambda alt: ("Other precoding scheme", "95th", alt, "70%RU")
    assert ws[f"D{r[key('Alt1s')]}"].value == 0
    assert ws[f"D{r[key('Alt3')]}"].value == pytest.approx(
        gain("svd_20ms", "70", "irc-fix-warmfast", "per_layer", "upt_p95") / 100)
