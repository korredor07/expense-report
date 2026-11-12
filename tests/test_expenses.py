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
    currency_totals,
    format_totals,
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

    def test_prints_currency_totals(self) -> None:
        path = write_csv(
            "date,description,amount,currency\n"
            "2026-10-03,Taxi,12.50,USD\n"
            "2026-10-05,Lunch,9,EUR\n"
            "2026-10-06,Bus,1000,COP\n"
        )
        out = self.run_cli(str(path))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            out.stdout.splitlines(),
            ["3 expenses from 2026-10-03 to 2026-10-06", "COP 1000.00", "EUR 9.00", "USD 12.50"],
        )

    def test_empty_csv_prints_only_no_expenses(self) -> None:
        path = write_csv("date,description,amount,currency\n")
        out = self.run_cli(str(path))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["No expenses."])


def exp(amount: str, currency: str) -> Expense:
    return Expense(date(2026, 10, 3), "x", Decimal(amount), currency)


class CurrencyTotals(unittest.TestCase):
    def test_sums_per_currency(self) -> None:
        totals = dict(currency_totals([exp("100.40", "EUR"), exp("41.50", "EUR")]))
        self.assertEqual(totals["EUR"], Decimal("141.90"))

    def test_currencies_not_mixed(self) -> None:
        totals = dict(currency_totals([exp("5", "USD"), exp("7", "EUR")]))
        self.assertEqual(totals, {"USD": Decimal("5.00"), "EUR": Decimal("7.00")})

    def test_sorted_by_code(self) -> None:
        result = currency_totals([exp("1", "USD"), exp("1", "EUR"), exp("1", "COP")])
        self.assertEqual([c for c, _ in result], ["COP", "EUR", "USD"])

    def test_exact_decimal_and_two_places(self) -> None:
        result = currency_totals([exp("0.10", "USD"), exp("0.20", "USD")])
        self.assertEqual(result, [("USD", Decimal("0.30"))])
        self.assertEqual(str(currency_totals([exp("9", "EUR")])[0][1]), "9.00")

    def test_formatted_line(self) -> None:
        lines = format_totals([exp("100.40", "EUR"), exp("41.50", "EUR")])
        self.assertEqual(lines, ["EUR 141.90"])

    def test_empty(self) -> None:
        self.assertEqual(currency_totals([]), [])
        self.assertEqual(format_totals([]), [])


if __name__ == "__main__":
    unittest.main()
