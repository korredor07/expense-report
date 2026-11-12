import io
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from report.expenses import Expense, ReportError, read_expenses

JSON_TWO = (
    '[{"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"},'
    ' {"date": "2026-10-05", "description": "Lunch", "amount": 9, "currency": "eur"}]'
)

XML_TWO = (
    "<expenses>"
    "<expense><date>2026-10-03</date><description>Taxi</description>"
    "<amount>12.50</amount><currency>usd</currency></expense>"
    "<expense><date>2026-10-05</date><description>Lunch</description>"
    "<amount>9</amount><currency>EUR</currency></expense>"
    "</expenses>"
)

XLSX_ROWS = [
    ["date", "description", "amount", "currency"],
    ["2026-10-03", "Taxi", 12.5, "USD"],
    ["2026-10-05", "Lunch", 9, "EUR"],
]

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
MAIN_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
PKG_NS = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
CONTENT_TYPES = f'{XML_HEADER}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
WORKBOOK = (
    f'{XML_HEADER}<workbook {MAIN_NS} {REL_NS}>'
    '<sheets><sheet name="Expenses" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
WORKBOOK_RELS = (
    f'{XML_HEADER}<Relationships {PKG_NS}>'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
    ' Target="worksheets/sheet1.xml"/></Relationships>'
)


def xlsx_bytes(rows: list[list]) -> bytes:
    """Build a one-sheet workbook. A str cell becomes a shared string, a number becomes a numeric cell."""
    strings: list[str] = []
    sheet_rows = []
    for number, cells in enumerate(rows, start=1):
        xml_cells = []
        for col, value in enumerate(cells):
            ref = f"{chr(65 + col)}{number}"
            if isinstance(value, str):
                if value not in strings:
                    strings.append(value)
                xml_cells.append(f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>')
            else:
                xml_cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        sheet_rows.append(f'<row r="{number}">{"".join(xml_cells)}</row>')
    sheet = f'{XML_HEADER}<worksheet {MAIN_NS}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    items = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    shared = f'{XML_HEADER}<sst {MAIN_NS}>{items}</sst>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        zf.writestr("xl/sharedStrings.xml", shared)
    return buf.getvalue()


class Files(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, data: str | bytes) -> Path:
        path = self.dir / name
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path


class Dispatch(Files):
    def test_reads_each_format_by_extension(self) -> None:
        self.assertEqual(len(read_expenses(self.write("e.json", JSON_TWO))), 2)
        self.assertEqual(len(read_expenses(self.write("e.xml", XML_TWO))), 2)
        self.assertEqual(len(read_expenses(self.write("e.xlsx", xlsx_bytes(XLSX_ROWS)))), 2)

    def test_extension_is_case_insensitive(self) -> None:
        self.assertEqual(len(read_expenses(self.write("E.JSON", JSON_TWO))), 2)

    def test_unknown_extension_names_it(self) -> None:
        for name in ("old.xls", "notes.txt"):
            with self.subTest(name=name):
                path = self.write(name, "whatever")
                with self.assertRaisesRegex(ReportError, re.escape(Path(name).suffix)):
                    read_expenses(path)


class Json(Files):
    def test_reads_two_records(self) -> None:
        expected = [
            Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"),
            Expense(date(2026, 10, 5), "Lunch", Decimal("9"), "EUR"),
        ]
        self.assertEqual(read_expenses(self.write("e.json", JSON_TWO)), expected)

    def test_amount_number_is_decimal_not_float(self) -> None:
        text = '[{"date": "2026-10-03", "description": "Taxi", "amount": 12.50, "currency": "USD"}]'
        amount = read_expenses(self.write("e.json", text))[0].amount
        self.assertIsInstance(amount, Decimal)
        self.assertEqual(str(amount), "12.50")

    def test_bad_record_names_line_3(self) -> None:
        text = JSON_TWO.replace('"2026-10-05"', '"05/10/2026"')
        with self.assertRaisesRegex(ReportError, "line 3"):
            read_expenses(self.write("e.json", text))

    def test_record_must_be_an_object(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(self.write("e.json", "[1]"))

    def test_invalid_json(self) -> None:
        with self.assertRaisesRegex(ReportError, "e.json"):
            read_expenses(self.write("e.json", "[{"))

    def test_top_level_must_be_an_array(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(self.write("e.json", '{"date": "2026-10-03"}'))


class Xml(Files):
    def test_reads_two_expenses(self) -> None:
        expenses = read_expenses(self.write("e.xml", XML_TWO))
        self.assertEqual([e.currency for e in expenses], ["USD", "EUR"])
        self.assertEqual([e.amount for e in expenses], [Decimal("12.50"), Decimal("9")])

    def test_bad_second_expense_names_line_3(self) -> None:
        variants = {
            "missing amount": XML_TWO.replace("<amount>9</amount>", ""),
            "bad amount": XML_TWO.replace("<amount>9</amount>", "<amount>nine</amount>"),
        }
        for label, text in variants.items():
            with self.subTest(label):
                with self.assertRaisesRegex(ReportError, "line 3"):
                    read_expenses(self.write("e.xml", text))

    def test_malformed_xml(self) -> None:
        with self.assertRaisesRegex(ReportError, "e.xml"):
            read_expenses(self.write("e.xml", "<expenses><expense>"))


class Xlsx(Files):
    def test_reads_shared_text_and_numeric_cells(self) -> None:
        expenses = read_expenses(self.write("e.xlsx", xlsx_bytes(XLSX_ROWS)))
        self.assertEqual(
            expenses,
            [
                Expense(date(2026, 10, 3), "Taxi", Decimal("12.5"), "USD"),
                Expense(date(2026, 10, 5), "Lunch", Decimal("9"), "EUR"),
            ],
        )

    def test_date_serial_number(self) -> None:
        rows = [XLSX_ROWS[0], [46300, "Taxi", 12.5, "USD"]]
        self.assertEqual(read_expenses(self.write("e.xlsx", xlsx_bytes(rows)))[0].day, date(2026, 10, 5))

    def test_bad_amount_in_row_3_names_line_3(self) -> None:
        rows = XLSX_ROWS[:2] + [["2026-10-05", "Lunch", "x", "EUR"]]
        with self.assertRaisesRegex(ReportError, "line 3"):
            read_expenses(self.write("e.xlsx", xlsx_bytes(rows)))

    def test_file_that_is_not_a_zip(self) -> None:
        with self.assertRaisesRegex(ReportError, "e.xlsx"):
            read_expenses(self.write("e.xlsx", b"not a zip file"))

    def test_workbook_without_worksheet(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("xl/workbook.xml", f'{XML_HEADER}<workbook {MAIN_NS} {REL_NS}><sheets/></workbook>')
        with self.assertRaisesRegex(ReportError, "e.xlsx"):
            read_expenses(self.write("e.xlsx", buf.getvalue()))


class Cli(Files):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_the_summary_for_each_format(self) -> None:
        files = {
            "e.json": JSON_TWO.encode("utf-8"),
            "e.xml": XML_TWO.encode("utf-8"),
            "e.xlsx": xlsx_bytes(XLSX_ROWS),
        }
        for name, data in files.items():
            with self.subTest(name=name):
                out = self.run_cli(str(self.write(name, data)))
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn("2 expenses from 2026-10-03 to 2026-10-05", out.stdout)

    def test_unsupported_extension_exits_1(self) -> None:
        out = self.run_cli(str(self.write("old.xls", b"x")))
        self.assertEqual(out.returncode, 1)
        self.assertIn("error:", out.stderr)


if __name__ == "__main__":
    unittest.main()
