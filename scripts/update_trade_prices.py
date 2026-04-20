"""Update latest price fields in trades/*.md from a portfolio report.

This is intentionally narrower than fill-trades:
- fill-trades fills blanks only.
- update_trade_prices refreshes market fields in the metadata/basic-info block.

Only these fields are touched:
- 目前價格
- 月線 (20MA) / 月線 (20MA) 位置
- 預估殖利率 / 現價殖利率 / 殖利率
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sys

from md_lib import Section, load_outline, read_text, replace_section, section_text


PRICE_RE = re.compile(r"^- \*\*目前價格\*\*:\s*(.*)$")
MA20_RE = re.compile(r"^- \*\*月線 \(20MA\)(?: 位置)?\*\*:\s*(.*)$")
YIELD_RE = re.compile(r"^- \*\*(預估殖利率|現價殖利率|殖利率)\*\*:\s*(.*)$")
REPORT_ROW_RE = re.compile(
    r"^\| `(?P<code>\d+)` \| (?P<name>.*?) \| "
    r"(?P<price>[0-9,.]+) \| (?P<ma20>[0-9,.]+) \| "
    r"(?P<pnl>[^|]+) \| (?P<yield>[^|]+) \|"
)


@dataclass
class ReportRow:
    code: str
    name: str
    price: str
    ma20: str
    dividend_yield: str


@dataclass
class UpdateResult:
    path: Path
    code: str
    status: str
    changes: list[str]
    reason: str = ""


def parse_report(path: Path) -> dict[str, ReportRow]:
    text = read_text(path)
    # Stop before budget tables, because they also start with code/name columns.
    text = text.split("## 💼 資金桶檢查", 1)[0]

    rows: dict[str, ReportRow] = {}
    for line in text.splitlines():
        match = REPORT_ROW_RE.match(line)
        if not match:
            continue
        rows[match.group("code")] = ReportRow(
            code=match.group("code"),
            name=match.group("name").strip(),
            price=match.group("price").replace(",", "").strip(),
            ma20=match.group("ma20").replace(",", "").strip(),
            dividend_yield=match.group("yield").strip(),
        )
    return rows


def format_market_number(value: str) -> str:
    raw = value.replace(",", "").strip()
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return value.strip()

    decimals = 0
    if "." in raw:
        decimals = len(raw.split(".", 1)[1])
    return f"{number:,.{decimals}f}"


def latest_report() -> Path | None:
    candidates = sorted(Path(".").glob("持倉健診_*.md"), reverse=True)
    return candidates[0] if candidates else None


def code_from_trade_path(path: Path) -> str:
    return path.name.split("_", 1)[0]


def find_basic_section(path: Path) -> Section | None:
    for section in load_outline(path):
        if section.level == 2 and section.title.strip() == "基本資訊":
            return section
    return None


def legacy_header_section(text: str) -> Section | None:
    lines = text.splitlines()
    if not lines:
        return None

    end = len(lines)
    for idx, line in enumerate(lines[1:], start=2):
        if line.startswith("## "):
            end = idx - 1
            break
    while end > 1 and lines[end - 1].strip() == "":
        end -= 1

    header_lines = lines[:end]
    if any(PRICE_RE.match(line) or MA20_RE.match(line) or YIELD_RE.match(line) for line in header_lines):
        return Section(level=1, title="legacy header", line=1, end_line=end)
    return None


def update_block(block: str, row: ReportRow, as_of: str) -> tuple[str, list[str]]:
    lines = block.splitlines()
    changes: list[str] = []
    price = format_market_number(row.price)
    ma20 = format_market_number(row.ma20)

    price_seen = False
    ma20_seen = False
    yield_seen = False
    ma20_index: int | None = None

    for i, line in enumerate(lines):
        price_match = PRICE_RE.match(line)
        if price_match:
            price_seen = True
            new_line = f"- **目前價格**: {price} 元 ({as_of})"
            if line != new_line:
                changes.append(f"目前價格: {price_match.group(1).strip()} -> {price} 元 ({as_of})")
                lines[i] = new_line
            continue

        ma20_match = MA20_RE.match(line)
        if ma20_match:
            ma20_seen = True
            ma20_index = i
            new_line = f"- **月線 (20MA) 位置**: {ma20} 元 ({as_of})"
            if line != new_line:
                changes.append(f"月線: {ma20_match.group(1).strip()} -> {ma20} 元 ({as_of})")
                lines[i] = new_line
            continue

        yield_match = YIELD_RE.match(line)
        if yield_match:
            yield_seen = True
            label = yield_match.group(1)
            old_value = yield_match.group(2).strip()
            suffix = ""
            if " / " in old_value:
                suffix = " / " + old_value.split(" / ", 1)[1].strip()
            new_value = f"{row.dividend_yield}{suffix}"
            new_line = f"- **{label}**: {new_value}"
            if line != new_line:
                changes.append(f"{label}: {old_value} -> {new_value}")
                lines[i] = new_line

    if not price_seen:
        changes.append(f"新增目前價格: {price} 元 ({as_of})")
        insert_at = 1 if lines and lines[0].startswith("## ") else len(lines)
        lines.insert(insert_at, f"- **目前價格**: {price} 元 ({as_of})")
        if ma20_index is not None and ma20_index >= insert_at:
            ma20_index += 1

    if not ma20_seen:
        changes.append(f"新增月線: {ma20} 元 ({as_of})")
        insert_at = ma20_index + 1 if ma20_index is not None else len(lines)
        lines.insert(insert_at, f"- **月線 (20MA) 位置**: {ma20} 元 ({as_of})")
        ma20_index = insert_at

    if not yield_seen:
        changes.append(f"新增預估殖利率: {row.dividend_yield}")
        insert_at = ma20_index + 1 if ma20_index is not None else len(lines)
        lines.insert(insert_at, f"- **預估殖利率**: {row.dividend_yield}")

    return "\n".join(lines), changes


def update_trade_file(path: Path, row: ReportRow, as_of: str) -> tuple[str, list[str], str]:
    text = read_text(path)
    section = find_basic_section(path)
    mode = "基本資訊"
    if section is None:
        section = legacy_header_section(text)
        mode = "legacy header"
    if section is None:
        return text, [], "no 基本資訊 section or recognized legacy header"

    block = section_text(text, section, include_heading=True)
    updated_block, changes = update_block(block, row, as_of)
    if not changes:
        return text, [], mode

    updated_text = replace_section(text, section, updated_block, content_includes_heading=True)
    return updated_text, changes, mode


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh trade MD market fields from 持倉健診 report.")
    parser.add_argument("--report", help="Report path. Defaults to latest 持倉健診_*.md in repo root.")
    parser.add_argument("--trades-dir", default="trades", help="Directory containing trade markdown files.")
    parser.add_argument("--as-of", help="Date to write in fields. Defaults to date parsed from report filename or today.")
    parser.add_argument("--code", action="append", help="Only update this code. Can be repeated.")
    parser.add_argument("--write", action="store_true", help="Write changes. Default is dry-run.")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else latest_report()
    if report_path is None or not report_path.exists():
        print("ERROR: report not found. Pass --report 持倉健診_YYYY-MM-DD.md", file=sys.stderr)
        return 2

    as_of = args.as_of
    if not as_of:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", report_path.name)
        as_of = match.group(1) if match else date.today().isoformat()

    rows = parse_report(report_path)
    if not rows:
        print(f"ERROR: no holding rows parsed from {report_path}", file=sys.stderr)
        return 1

    selected_codes = set(args.code or [])
    trade_paths = sorted(Path(args.trades_dir).glob("*.md"))
    results: list[UpdateResult] = []

    for path in trade_paths:
        if path.name == "template.md":
            continue
        code = code_from_trade_path(path)
        if selected_codes and code not in selected_codes:
            continue
        row = rows.get(code)
        if row is None:
            results.append(UpdateResult(path, code, "skipped", [], "not in report"))
            continue

        updated_text, changes, reason = update_trade_file(path, row, as_of)
        if not changes:
            results.append(UpdateResult(path, code, "unchanged", [], reason))
            continue

        if args.write:
            path.write_text(updated_text, encoding="utf-8")
        results.append(UpdateResult(path, code, "updated" if args.write else "would-update", changes, reason))

    changed = [r for r in results if r.status in {"updated", "would-update"}]
    skipped = [r for r in results if r.status == "skipped"]
    unchanged = [r for r in results if r.status == "unchanged"]

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"=== update_trade_prices {mode} ===")
    print(f"report: {report_path}")
    print(f"as_of: {as_of}")
    print(f"parsed rows: {len(rows)}")
    print(f"changed: {len(changed)} | unchanged: {len(unchanged)} | skipped: {len(skipped)}")

    for result in changed:
        print(f"\n[{result.status}] {result.path} ({result.reason})")
        for change in result.changes:
            print(f"  - {change}")

    if skipped:
        print("\nskipped:")
        for result in skipped:
            print(f"  - {result.path}: {result.reason}")

    if not args.write:
        print("\nNo files written. Re-run with --write to apply changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
