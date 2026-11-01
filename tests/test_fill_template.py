"""examples/fill_cw2l_template.write_cells: values land in the right cells
and every other part of the workbook is left as it was."""

import os
import sys
import zipfile

import openpyxl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from fill_cw2l_template import write_cells  # noqa: E402


@pytest.fixture
def book(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SLS rank 1-4"
    ws["A1"], ws["D1"], ws["D3"] = "label", "Company X", None
    ws["D3"].font = openpyxl.styles.Font(bold=True)        # styled empty cell
    ws["C5"] = "70%RU"
    wb.create_sheet("other")["A1"] = "untouched"
    path = tmp_path / "t.xlsx"
    wb.save(path)
    return path


def test_write_cells_values_and_other_parts_unchanged(book):
    before = {i.filename: zipfile.ZipFile(book).read(i.filename)
              for i in zipfile.ZipFile(book).infolist()}
    write_cells(str(book), {"D1": "nrsls & <IRC>", "D3": -0.0573, "E3": 0.0,
                            "E5": 0.1052, "B5": "left of C"})
    z = zipfile.ZipFile(book)
    after = {i.filename: z.read(i.filename) for i in z.infolist()}
    assert list(after) == list(before)
    changed = {f for f in before if before[f] != after[f]}
    assert changed == {"xl/worksheets/sheet1.xml", "xl/styles.xml"}

    ws = openpyxl.load_workbook(book)["SLS rank 1-4"]
    assert ws["D1"].value == "nrsls & <IRC>" and ws["A1"].value == "label"
    assert ws["D3"].value == pytest.approx(-0.0573) and ws["D3"].number_format == "0.0%"
    assert ws["D3"].font.bold                               # keeps the cell's own style
    assert ws["E3"].value == 0 and ws["E3"].number_format == "0.0%"
    assert ws["E5"].value == pytest.approx(0.1052) and ws["C5"].value == "70%RU"
    assert ws["B5"].value == "left of C"
    assert openpyxl.load_workbook(book)["other"]["A1"].value == "untouched"
