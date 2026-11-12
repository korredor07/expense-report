import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import Expense, ReportError, parse_row, read_expenses, summary

ROW = {"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"}


def write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


class ParseRow(unittest.TestCase):
    def test_reads_a_row(self) -> None:
        self.assertEqual(parse_row(ROW, 2), Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"))

    def test_bad_date_names_the_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 7"):
            parse_row({**ROW, "date": "03/10/2026"}, 7)

    def test_bad_amount(self) -> None:
        with self.assertRaises(ReportError):
            parse_row({**ROW, "amount": "twelve"}, 2)

    def test_bad_currency(self) -> None:
        with self.assertRaisesRegex(ReportError, "3-letter"):
            parse_row({**ROW, "currency": "dollars"}, 2)


class ReadAndSummarise(unittest.TestCase):
    def test_reads_a_file(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,12.50,USD\n2026-10-05,Lunch,9,EUR\n")
        self.assertEqual([e.currency for e in read_expenses(path)], ["USD", "EUR"])

    def test_error_line_counts_the_header(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,x,USD\n")
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(path)

    def test_summary(self) -> None:
        expenses = [parse_row(ROW, 2), parse_row({**ROW, "date": "2026-09-30"}, 3)]
        self.assertEqual(summary(expenses), "2 expenses from 2026-09-30 to 2026-10-03")

    def test_summary_of_nothing(self) -> None:
        self.assertEqual(summary([]), "No expenses.")


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


HEADER = ["date", "description", "amount", "currency"]
ROWS = [["2026-10-03", "Taxi", "12.50", "USD"], ["2026-10-05", "Lunch", "9", "EUR"]]
EXPECTED = [
    Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"),
    Expense(date(2026, 10, 5), "Lunch", Decimal("9"), "EUR"),
]


def write_file(name: str, text: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def csv_file(rows: list[list[str]], name: str = "e.csv") -> Path:
    return write_file(name, "\n".join(",".join(r) for r in [HEADER, *rows]) + "\n")


def json_file(rows: list[list[str]], name: str = "e.json") -> Path:
    import json

    return write_file(name, json.dumps([dict(zip(HEADER, r)) for r in rows]))


def xml_file(rows: list[list[str]], name: str = "e.xml") -> Path:
    body = "".join(
        "<expense>" + "".join(f"<{k}>{v}</{k}>" for k, v in zip(HEADER, r)) + "</expense>" for r in rows
    )
    return write_file(name, f"<expenses>{body}</expenses>")


def xlsx_file(rows: list[list[str]], name: str = "e.xlsx") -> Path:
    import zipfile

    strings: list[str] = []
    sheet_rows = []
    for n, r in enumerate([HEADER, *rows], start=1):
        cells = ""
        for c, v in enumerate(r):
            if v not in strings:
                strings.append(v)
            cells += f'<c r="{"ABCD"[c]}{n}" t="s"><v>{strings.index(v)}</v></c>'
        sheet_rows.append(f'<row r="{n}">{cells}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sst = f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    sheet = f'<worksheet {ns}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    p = Path(tempfile.mkdtemp()) / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return p


class Formats(unittest.TestCase):
    def test_csv_uppercase_extension(self) -> None:
        self.assertEqual(read_expenses(csv_file(ROWS, "E.CSV")), EXPECTED)

    def test_all_formats_equal(self) -> None:
        for make in (csv_file, json_file, xml_file, xlsx_file):
            with self.subTest(make.__name__):
                self.assertEqual(read_expenses(make(ROWS)), EXPECTED)

    def test_json_number_amount(self) -> None:
        p = write_file("n.json", '[{"date":"2026-10-03","description":"T","amount":12.5,"currency":"USD"}]')
        self.assertEqual(read_expenses(p)[0].amount, Decimal("12.5"))

    def test_json_bad_amount_line(self) -> None:
        bad = [ROWS[0], ["2026-10-05", "Lunch", "x", "EUR"]]
        with self.assertRaisesRegex(ReportError, "line 3"):
            read_expenses(json_file(bad))

    def test_json_invalid(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("b.json", "{not json"))

    def test_json_not_array(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("b.json", "{}"))

    def test_xml_bad_date_line(self) -> None:
        bad = [ROWS[0], ["nope", "Lunch", "9", "EUR"]]
        with self.assertRaisesRegex(ReportError, "line 3"):
            read_expenses(xml_file(bad))

    def test_xml_malformed(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("b.xml", "<a><b>"))

    def test_xlsx_bad_row_line(self) -> None:
        bad = [ROWS[0], ["2026-10-05", "Lunch", "x", "EUR"]]
        with self.assertRaisesRegex(ReportError, "line 3"):
            read_expenses(xlsx_file(bad))

    def test_xlsx_not_a_zip(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("b.xlsx", "plain text"))

    def test_unknown_extension(self) -> None:
        for name in ("e.txt", "noext", "e.xls"):
            with self.subTest(name), self.assertRaisesRegex(ReportError, "csv"):
                read_expenses(write_file(name, "x"))

    def test_cli_formats(self) -> None:
        for make in (json_file, xml_file, xlsx_file):
            out = Cli().run_cli(str(make(ROWS)))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("expenses from", out.stdout)

    def test_cli_unsupported(self) -> None:
        self.assertEqual(Cli().run_cli(str(write_file("e.txt", "x"))).returncode, 1)


if __name__ == "__main__":
    unittest.main()
