import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import Expense, ReportError, parse_row, read_expenses, summary, summary_data, totals

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

    def test_json_output(self) -> None:
        out = self.run_cli("data/sample.csv", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(set(data), {"count", "from", "to", "totals"})
        for value in data["totals"].values():
            self.assertIsInstance(value, str)
            self.assertRegex(value, r"^-?\d+\.\d{2}$")

    def test_json_flag_before_file(self) -> None:
        self.assertEqual(self.run_cli("--json", "data/sample.csv").stdout, self.run_cli("data/sample.csv", "--json").stdout)

    def test_json_missing_file(self) -> None:
        out = self.run_cli("missing.csv", "--json")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout, "")

    def test_json_exact(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-05,A,0.10,USD\n2026-10-03,B,0.20,USD\n2026-10-04,C,9,EUR\n")
        out = self.run_cli(str(path), "--json")
        expected = {"count": 3, "from": "2026-10-03", "to": "2026-10-05", "totals": {"EUR": "9.00", "USD": "0.30"}}
        self.assertEqual(json.loads(out.stdout), expected)


class JsonData(unittest.TestCase):
    def test_totals_per_currency(self) -> None:
        rows = [parse_row(ROW, 2), parse_row({**ROW, "amount": "7.25"}, 3), parse_row({**ROW, "currency": "eur"}, 4)]
        self.assertEqual(totals(rows), {"EUR": "12.50", "USD": "19.75"})

    def test_totals_two_decimals(self) -> None:
        rows = [parse_row({**ROW, "amount": "9"}, 2), parse_row({**ROW, "amount": "0.10", "currency": "eur"}, 3),
                parse_row({**ROW, "amount": "0.20", "currency": "eur"}, 4)]
        self.assertEqual(totals(rows), {"EUR": "0.30", "USD": "9.00"})

    def test_summary_data(self) -> None:
        rows = [parse_row(ROW, 2), parse_row({**ROW, "date": "2026-09-30"}, 3)]
        self.assertEqual(
            summary_data(rows),
            {"count": 2, "from": "2026-09-30", "to": "2026-10-03", "totals": {"USD": "25.00"}},
        )

    def test_summary_data_empty(self) -> None:
        self.assertEqual(summary_data([]), {"count": 0, "from": None, "to": None, "totals": {}})


if __name__ == "__main__":
    unittest.main()
