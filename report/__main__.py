"""python3 -m report [--by-month] <file.csv>"""

from __future__ import annotations

import sys
from pathlib import Path

from report.expenses import ReportError, format_monthly, monthly_totals, read_expenses, summary

USAGE = "usage: python3 -m report [--by-month] <file.csv>"


def main(argv: list[str]) -> int:
    by_month = "--by-month" in argv
    args = [a for a in argv if a != "--by-month"]
    if len(args) != 1 or args[0].startswith("--"):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        expenses = read_expenses(Path(args[0]))
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_monthly(monthly_totals(expenses)) if by_month else summary(expenses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
