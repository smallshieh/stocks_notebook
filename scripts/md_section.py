"""Print one or more Markdown sections selected by heading title."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from md_lib import (
    find_sections,
    load_outline,
    read_text,
    section_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read only selected Markdown section(s) by heading title."
    )
    parser.add_argument("file", help="Markdown file path")
    parser.add_argument("section", nargs="?", help="Heading title or substring")
    parser.add_argument("--section", dest="sections", action="append", help="Additional heading title or substring")
    parser.add_argument("--exact", action="store_true", help="Require exact normalized title match")
    parser.add_argument("--level", type=int, choices=range(1, 7), help="Restrict heading level")
    parser.add_argument("--all", action="store_true", help="Return all matching sections")
    parser.add_argument("--no-heading", action="store_true", help="Omit the section heading line")
    parser.add_argument("--json", action="store_true", help="Output JSON with metadata and content")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    queries: list[str] = []
    if args.section:
        queries.append(args.section)
    if args.sections:
        queries.extend(args.sections)
    if not queries:
        parser.error("provide a section title or --section")

    text = read_text(path)
    outline = load_outline(path)
    results = []
    for query in queries:
        matches = find_sections(outline, query, exact=args.exact, level=args.level)
        if not matches:
            print(f"ERROR: no section matched: {query}", file=sys.stderr)
            return 1
        if len(matches) > 1 and not args.all:
            print(f"ERROR: multiple sections matched: {query}", file=sys.stderr)
            for section in matches:
                print(f"  L{section.line:03d} H{section.level} {section.title} [{section.line}-{section.end_line}]", file=sys.stderr)
            print("Use --all or --exact/--level to disambiguate.", file=sys.stderr)
            return 1
        selected = matches if args.all else matches[:1]
        for section in selected:
            content = section_text(text, section, include_heading=not args.no_heading)
            results.append({"section": section.to_dict(), "content": content})

    if args.json:
        print(json.dumps({"file": str(path), "results": results}, ensure_ascii=False, indent=2))
    else:
        chunks = []
        for item in results:
            section = item["section"]
            chunks.append(
                f"<!-- {path} L{section['line']}-L{section['end_line']} -->\n"
                f"{item['content']}"
            )
        print("\n\n".join(chunks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
