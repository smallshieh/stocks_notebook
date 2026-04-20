"""Small Markdown section parser for agent-friendly file reads.

The parser intentionally handles only Markdown ATX headings (`# Heading`).
It ignores headings inside fenced code blocks and returns 1-based line ranges.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
from typing import Iterable


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    level: int
    title: str
    line: int
    end_line: int

    def to_dict(self) -> dict:
        return asdict(self)


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def split_lines(text: str) -> list[str]:
    return text.splitlines()


def parse_outline(text: str) -> list[Section]:
    lines = split_lines(text)
    headings: list[tuple[int, str, int]] = []
    in_fence = False

    for idx, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((level, title, idx))

    sections: list[Section] = []
    for i, (level, title, start) in enumerate(headings):
        end = len(lines)
        for next_level, _next_title, next_start in headings[i + 1 :]:
            if next_level <= level:
                end = next_start - 1
                break
        sections.append(Section(level=level, title=title, line=start, end_line=end))
    return sections


def load_outline(path: str | Path) -> list[Section]:
    return parse_outline(read_text(path))


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def find_sections(
    sections: Iterable[Section],
    query: str,
    *,
    exact: bool = False,
    level: int | None = None,
) -> list[Section]:
    needle = normalize_title(query)
    candidates: list[Section] = []
    for section in sections:
        if level is not None and section.level != level:
            continue
        candidates.append(section)

    exact_matches: list[Section] = []
    fuzzy_matches: list[Section] = []
    for section in candidates:
        haystack = normalize_title(section.title)
        if haystack == needle:
            exact_matches.append(section)
        elif needle in haystack:
            fuzzy_matches.append(section)

    if exact:
        return exact_matches
    return exact_matches or fuzzy_matches


def section_text(text: str, section: Section, *, include_heading: bool = True) -> str:
    lines = split_lines(text)
    start = section.line if include_heading else section.line + 1
    if start > section.end_line:
        return ""
    return "\n".join(lines[start - 1 : section.end_line])


def replace_section(
    text: str,
    section: Section,
    new_content: str,
    *,
    content_includes_heading: bool = True,
) -> str:
    lines = split_lines(text)
    replacement = new_content.rstrip("\n").splitlines()
    if not content_includes_heading:
        heading = lines[section.line - 1]
        replacement = [heading] + replacement

    before = lines[: section.line - 1]
    after = lines[section.end_line :]
    trailing_newline = "\n" if text.endswith(("\n", "\r\n")) else ""
    return "\n".join(before + replacement + after) + trailing_newline


def sections_json(path: str | Path, sections: Iterable[Section]) -> str:
    data = {
        "file": str(path),
        "sections": [section.to_dict() for section in sections],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
