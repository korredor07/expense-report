"""Read expenses from CSV, JSON, XML or XLSX files (date, description, amount, currency) and summarise them."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
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


EXCEL_EPOCH = date(1899, 12, 30)
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


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


def read_csv(path: Path) -> list[Expense]:
    with path.open(newline="", encoding="utf-8") as f:
        return [parse_row(row, n) for n, row in enumerate(csv.DictReader(f), start=2)]


def read_json(path: Path) -> list[Expense]:
    try:
        data = json.loads(path.read_bytes(), parse_float=Decimal)
    except ValueError as exc:
        raise ReportError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(data, list):
        raise ReportError(f"{path.name}: top level must be an array of expenses")
    return [parse_row(_text_row(record, n), n) for n, record in enumerate(data, start=2)]


def _text_row(record: object, line: int) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ReportError(f"line {line}: expense must be an object")
    return {key: "" if value is None else str(value) for key, value in record.items()}


def read_xml(path: Path) -> list[Expense]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ReportError(f"{path.name}: not valid XML ({exc})") from exc
    rows = [{child.tag: child.text or "" for child in element} for element in root]
    return [parse_row(row, n) for n, row in enumerate(rows, start=2)]


def read_xlsx(path: Path) -> list[Expense]:
    try:
        grid = _read_grid(path)
    except (zipfile.BadZipFile, ET.ParseError, ReportError, IndexError, ValueError) as exc:
        raise ReportError(f"{path.name}: not a readable .xlsx workbook ({exc})") from exc
    if not grid or not grid[0][1]:
        raise ReportError(f"{path.name}: worksheet has no header row")
    header = {col: text.strip() for col, (text, _) in grid[0][1].items()}
    records = [
        (number, _record(header, cells))
        for number, cells in grid[1:]
        if any(text.strip() for text, _ in cells.values())
    ]
    return [parse_row(record, n) for n, record in records]


def _read_grid(path: Path) -> list[tuple[int, dict[int, tuple[str, bool]]]]:
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        sheet = _first_sheet(zf)
    return [
        (int(row.get("r", position)), {_column(c.get("r", "")): _cell(c, strings) for c in row.findall(f"{MAIN}c")})
        for position, row in enumerate(sheet.iter(f"{MAIN}row"), start=1)
    ]


def _part(zf: zipfile.ZipFile, name: str) -> ET.Element:
    if name not in zf.namelist():
        raise ReportError(f"missing {name}")
    return ET.fromstring(zf.read(name))


def _first_sheet(zf: zipfile.ZipFile) -> ET.Element:
    sheet = _part(zf, "xl/workbook.xml").find(f"{MAIN}sheets/{MAIN}sheet")
    if sheet is None:
        raise ReportError("workbook has no worksheet")
    rels = _part(zf, "xl/_rels/workbook.xml.rels")
    return _part(zf, _sheet_target(rels, sheet.get(f"{REL}id")))


def _sheet_target(rels: ET.Element, rel_id: str | None) -> str:
    for rel in rels.iter(f"{PKG}Relationship"):
        if rel.get("Id") == rel_id:
            target = rel.get("Target", "")
            return target[1:] if target.startswith("/") else f"xl/{target}"
    raise ReportError("workbook has no worksheet")


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _part(zf, "xl/sharedStrings.xml")
    return ["".join(t.text or "" for t in si.iter(f"{MAIN}t")) for si in root.iter(f"{MAIN}si")]


def _column(ref: str) -> int:
    index = 0
    for ch in ref:
        if not ch.isalpha():
            break
        index = index * 26 + ord(ch.upper()) - ord("A") + 1
    return index


def _cell(cell: ET.Element, strings: list[str]) -> tuple[str, bool]:
    """Return a cell's text and whether it is a plain number (a candidate Excel date serial)."""
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{MAIN}t")), False
    value = cell.findtext(f"{MAIN}v", default="")
    if kind == "s":
        return strings[int(value)], False
    return value, kind in (None, "n")


def _record(header: dict[int, str], cells: dict[int, tuple[str, bool]]) -> dict[str, str]:
    record = {}
    for col, (text, numeric) in cells.items():
        if col in header:
            name = header[col]
            record[name] = _serial_to_iso(text) if numeric and name == "date" else text
    return record


def _serial_to_iso(text: str) -> str:
    try:
        return (EXCEL_EPOCH + timedelta(days=int(float(text)))).isoformat()
    except (ValueError, OverflowError):
        return text


READERS: dict[str, Callable[[Path], list[Expense]]] = {
    ".csv": read_csv,
    ".json": read_json,
    ".xml": read_xml,
    ".xlsx": read_xlsx,
}


def read_expenses(path: Path) -> list[Expense]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ReportError(f"unsupported file type {path.suffix!r}: use .csv, .json, .xlsx or .xml")
    return reader(path)


def summary(expenses: list[Expense]) -> str:
    if not expenses:
        return "No expenses."
    days = sorted(e.day for e in expenses)
    return f"{len(expenses)} expenses from {days[0].isoformat()} to {days[-1].isoformat()}"
