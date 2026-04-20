"""Print a compact Markdown heading outline with 1-based line ranges."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from md_lib import load_outline, sections_json


def format_outline(path: Path, *, min_level: int, max_level: int) -> str:
    sections = [
        s for s in load_outline(path)
        if s.level >= min_level and s.level <= max_level
    ]
    out = [str(path)]
    for section in sections:
        out.append(
            f"L{section.line:03d} H{section.level} {section.title} "
            f"[{section.line}-{section.end_line}]"
        )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Markdown headings and section line ranges."
    )
    parser.add_argument("files", nargs="+", help="Markdown file path(s)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--min-level", type=int, default=1, choices=range(1, 7))
    parser.add_argument("--max-level", type=int, default=6, choices=range(1, 7))
    args = parser.parse_args()

    if args.min_level > args.max_level:
        parser.error("--min-level cannot be greater than --max-level")

    chunks: list[str] = []
    for raw in args.files:
        path = Path(raw)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 2
        sections = [
            s for s in load_outline(path)
            if s.level >= args.min_level and s.level <= args.max_level
        ]
        if args.json:
            chunks.append(sections_json(path, sections))
        else:
            chunks.append(format_outline(path, min_level=args.min_level, max_level=args.max_level))

    print("\n\n".join(chunks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
