"""python3 -m report <file.csv> [--json]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from report.expenses import ReportError, read_expenses, summary, summary_data


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    files = [a for a in argv if a != "--json"]
    if len(files) != 1:
        print("usage: python3 -m report <file.csv> [--json]", file=sys.stderr)
        return 2
    try:
        expenses = read_expenses(Path(files[0]))
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary_data(expenses)) if as_json else summary(expenses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
