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
    format_monthly,
    monthly_totals,
    parse_row,
    read_expenses,
    summary,
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


def exp(day: str, amount: str, ccy: str = "USD") -> Expense:
    return Expense(date.fromisoformat(day), "x", Decimal(amount), ccy)


class MonthlyTotals(unittest.TestCase):
    def test_sums_within_a_month(self) -> None:
        got = monthly_totals([exp("2026-10-01", "1.50"), exp("2026-10-09", "2")])
        self.assertEqual(got, {"2026-10": {"USD": Decimal("3.50")}})

    def test_currencies_stay_separate(self) -> None:
        got = monthly_totals([exp("2026-10-01", "1", "USD"), exp("2026-10-02", "2", "EUR")])
        self.assertEqual(got["2026-10"], {"EUR": Decimal("2"), "USD": Decimal("1")})
        self.assertEqual(list(got["2026-10"]), ["EUR", "USD"])

    def test_splits_months(self) -> None:
        got = monthly_totals([exp("2026-09-30", "1"), exp("2026-10-01", "2")])
        self.assertEqual(set(got), {"2026-09", "2026-10"})

    def test_chronological_order(self) -> None:
        got = monthly_totals([exp("2026-10-01", "1"), exp("2025-12-01", "1"), exp("2026-02-01", "1")])
        self.assertEqual(list(got), ["2025-12", "2026-02", "2026-10"])

    def test_exact_decimal(self) -> None:
        got = monthly_totals([exp("2026-10-01", "0.10"), exp("2026-10-02", "0.20")])
        self.assertEqual(got["2026-10"]["USD"], Decimal("0.30"))

    def test_empty(self) -> None:
        self.assertEqual(monthly_totals([]), {})


class FormatMonthly(unittest.TestCase):
    def test_blocks(self) -> None:
        totals = {
            "2026-09": {"EUR": Decimal("9.00"), "USD": Decimal("30.00")},
            "2026-10": {"USD": Decimal("12.50")},
        }
        want = "2026-09\n  EUR 9.00\n  USD 30.00\n2026-10\n  USD 12.50"
        self.assertEqual(format_monthly(totals), want)

    def test_empty(self) -> None:
        self.assertEqual(format_monthly({}), "No expenses.")


class CliByMonth(unittest.TestCase):
    CSV = (
        "date,description,amount,currency\n"
        "2026-10-03,Taxi,12.50,USD\n2026-09-05,Lunch,9.00,EUR\n2026-09-06,Fly,30.00,USD\n"
    )
    WANT = "2026-09\n  EUR 9.00\n  USD 30.00\n2026-10\n  USD 12.50\n"

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_blocks(self) -> None:
        out = self.run_cli("--by-month", str(write_csv(self.CSV)))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, self.WANT)

    def test_flag_after_path(self) -> None:
        out = self.run_cli(str(write_csv(self.CSV)), "--by-month")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, self.WANT)

    def test_without_flag_is_summary(self) -> None:
        out = self.run_cli(str(write_csv(self.CSV)))
        self.assertIn("expenses from", out.stdout)

    def test_missing_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("--by-month", "missing.csv").returncode, 1)

    def test_bad_row_names_line(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,x,USD\n")
        out = self.run_cli("--by-month", str(path))
        self.assertEqual(out.returncode, 1)
        self.assertIn("line 2", out.stderr)

    def test_unknown_flag_exits_2(self) -> None:
        self.assertEqual(self.run_cli("--nope", "data/sample.csv").returncode, 2)

    def test_flag_without_file_exits_2(self) -> None:
        self.assertEqual(self.run_cli("--by-month").returncode, 2)


if __name__ == "__main__":
    unittest.main()
