"""Read expenses (date,description,amount,currency) from .csv, .json, .xlsx or .xml and summarise them."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class Expense:
    day: date
    description: str
    amount: Decimal
    currency: str


class ReportError(ValueError):
    """A row the report cannot use; the message names its line in the file."""


def parse_row(row: dict[str, str], line: int) -> Expense:
    try:
        day = date.fromisoformat(row["date"].strip())
        amount = Decimal(row["amount"].strip())
    except (KeyError, AttributeError, ValueError, InvalidOperation) as exc:
        raise ReportError(f"line {line}: cannot read date or amount ({exc})") from exc
    currency = (row.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ReportError(f"line {line}: currency must be a 3-letter code, got {currency!r}")
    return Expense(day, (row.get("description") or "").strip(), amount, currency)


FIELDS = ("date", "description", "amount", "currency")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _rows_csv(path: Path) -> list[tuple[int, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(enumerate(csv.DictReader(f), start=2))


def _rows_json(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=str, parse_int=str)
    except ValueError as exc:
        raise ReportError(f"line 1: invalid JSON ({exc})") from exc
    if not isinstance(data, list):
        raise ReportError("line 1: JSON must be an array of objects")
    rows = []
    for n, item in enumerate(data, start=2):
        if not isinstance(item, dict):
            raise ReportError(f"line {n}: expected a JSON object")
        rows.append((n, {k: v if isinstance(v, str) else str(v) for k, v in item.items() if v is not None}))
    return rows


def _rows_xml(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ReportError(f"line 1: invalid XML ({exc})") from exc
    return [(n, {k: (el.findtext(k) or "") for k in FIELDS if el.find(k) is not None})
            for n, el in enumerate(root, start=2)]


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in root.iter(f"{_NS}si")]


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{_NS}t"))
    value = cell.findtext(f"{_NS}v") or ""
    return strings[int(value)] if kind == "s" and value else value


def _rows_xlsx(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        with zipfile.ZipFile(path) as z:
            strings = _shared_strings(z)
            sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError, ValueError) as exc:
        raise ReportError(f"line 1: cannot read xlsx file ({exc})") from exc
    table = [[_cell_text(c, strings) for c in row] for row in sheet.iter(f"{_NS}row")]
    if not table:
        return []
    header = [h.strip().lower() for h in table[0]]
    return [(n, dict(zip(header, r))) for n, r in enumerate(table[1:], start=2)]


READERS = {".csv": _rows_csv, ".json": _rows_json, ".xml": _rows_xml, ".xlsx": _rows_xlsx}


def read_expenses(path: Path) -> list[Expense]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ReportError(f"unsupported file type {path.suffix!r}; supported: {', '.join(READERS)}")
    return [parse_row(row, n) for n, row in reader(path)]


def summary(expenses: list[Expense]) -> str:
    if not expenses:
        return "No expenses."
    days = sorted(e.day for e in expenses)
    return f"{len(expenses)} expenses from {days[0].isoformat()} to {days[-1].isoformat()}"
