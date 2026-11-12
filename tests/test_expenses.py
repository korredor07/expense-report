import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import (
    Expense,
    ReportError,
    format_expense,
    parse_row,
    read_expenses,
    summary,
    top_expenses,
)

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

    def test_top_on_sample(self) -> None:
        out = self.run_cli("data/sample.csv", "--top", "2")
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.strip().splitlines()
        self.assertIn("expenses from", lines[0])
        self.assertEqual(lines[1], "Top 2 expenses:")
        self.assertEqual(len(lines), 4)

    def test_top_exact_order(self) -> None:
        path = write_csv(
            "date,description,amount,currency\n"
            "2026-10-01,A,9.99,USD\n2026-10-02,B,10,EUR\n2026-10-03,C,5,USD\n"
        )
        out = self.run_cli(str(path), "--top", "2")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            out.stdout.strip().splitlines()[2:],
            ["2026-10-02  B  10 EUR", "2026-10-01  A  9.99 USD"],
        )

    def test_top_invalid_exits_2(self) -> None:
        for bad in (["0"], ["-3"], ["abc"], []):
            out = self.run_cli("data/sample.csv", "--top", *bad)
            self.assertEqual(out.returncode, 2, bad)
            self.assertIn("usage", out.stderr.lower())

    def test_no_top_only_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(len(out.stdout.strip().splitlines()), 1)

    def test_top_missing_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv", "--top", "1").returncode, 1)


class TopExpenses(unittest.TestCase):
    def make(self, *amounts: str) -> list[Expense]:
        return [Expense(date(2026, 10, 1), f"e{i}", Decimal(a), "USD") for i, a in enumerate(amounts)]

    def test_largest_descending(self) -> None:
        got = top_expenses(self.make("1", "5", "3"), 2)
        self.assertEqual([e.amount for e in got], [Decimal("5"), Decimal("3")])

    def test_n_larger_than_length(self) -> None:
        got = top_expenses(self.make("1", "5"), 10)
        self.assertEqual([e.amount for e in got], [Decimal("5"), Decimal("1")])

    def test_stable_on_ties(self) -> None:
        got = top_expenses(self.make("5", "5", "5"), 2)
        self.assertEqual([e.description for e in got], ["e0", "e1"])

    def test_decimal_comparison(self) -> None:
        got = top_expenses(self.make("9.99", "10"), 1)
        self.assertEqual(got[0].amount, Decimal("10"))

    def test_format_expense(self) -> None:
        e = Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD")
        self.assertEqual(format_expense(e), "2026-10-03  Taxi  12.50 USD")


if __name__ == "__main__":
    unittest.main()
