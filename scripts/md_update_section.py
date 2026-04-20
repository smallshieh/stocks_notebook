"""Replace a Markdown section by heading title.

Use this for targeted edits after inspecting a file with md_outline.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from md_lib import find_sections, load_outline, read_text, replace_section


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace one Markdown section safely.")
    parser.add_argument("file", help="Markdown file path")
    parser.add_argument("section", help="Heading title or substring")
    parser.add_argument("--from", dest="from_file", required=True, help="File containing replacement Markdown")
    parser.add_argument("--exact", action="store_true", help="Require exact normalized title match")
    parser.add_argument("--level", type=int, choices=range(1, 7), help="Restrict heading level")
    parser.add_argument("--body-only", action="store_true", help="Replacement file contains only the body; keep existing heading")
    parser.add_argument("--dry-run", action="store_true", help="Print updated content instead of writing")
    args = parser.parse_args()

    path = Path(args.file)
    replacement_path = Path(args.from_file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2
    if not replacement_path.exists():
        print(f"ERROR: replacement file not found: {replacement_path}", file=sys.stderr)
        return 2

    text = read_text(path)
    outline = load_outline(path)
    matches = find_sections(outline, args.section, exact=args.exact, level=args.level)
    if not matches:
        print(f"ERROR: no section matched: {args.section}", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print(f"ERROR: multiple sections matched: {args.section}", file=sys.stderr)
        for section in matches:
            print(f"  L{section.line:03d} H{section.level} {section.title} [{section.line}-{section.end_line}]", file=sys.stderr)
        print("Use --exact/--level to disambiguate.", file=sys.stderr)
        return 1

    replacement = read_text(replacement_path)
    updated = replace_section(
        text,
        matches[0],
        replacement,
        content_includes_heading=not args.body_only,
    )

    if args.dry_run:
        print(updated, end="")
    else:
        path.write_text(updated, encoding="utf-8")
        section = matches[0]
        print(f"updated {path}: L{section.line}-L{section.end_line} {section.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
