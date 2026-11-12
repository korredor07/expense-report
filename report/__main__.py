"""python3 -m report <file.csv> [--top N]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report.expenses import ReportError, format_expense, read_expenses, summary, top_expenses


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not an integer") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python3 -m report")
    parser.add_argument("file", type=Path, metavar="file.csv")
    parser.add_argument("--top", type=positive_int, metavar="N", help="also list the N largest expenses")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        expenses = read_expenses(args.file)
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(summary(expenses))
    if args.top and expenses:
        print(f"Top {args.top} expenses:")
        for e in top_expenses(expenses, args.top):
            print(format_expense(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
