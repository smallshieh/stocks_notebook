"""
hook_output.py — Structured JSON output format for hook scripts.

All hook scripts import this module to produce machine-readable results.
The hook_runner.py engine parses this output; Agent reads the structured summary.

Usage in a hook script:
    from hook_output import HookResult, HookTarget, output

    result = HookResult(
        hook="ma-breach-1210",
        timestamp="2026-05-05",
        status="alert",
        severity="high",
        targets=[
            HookTarget(
                code="1210", name="大成",
                action="p1_observe",
                summary="月線下方連續第 9 日",
                detail={"breach_days": 9, "ma20": 53.80, "current_price": 52.30}
            )
        ]
    )
    output(result)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class HookTarget:
    """A single stock-level signal within a hook result."""
    code: str
    name: str
    action: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """Top-level structured output from a hook script."""
    hook: str
    timestamp: str
    status: str                     # ok | alert | warning | error
    severity: str                   # high | medium | low
    targets: list[HookTarget] = field(default_factory=list)
    lifecycle_event: Optional[str] = None   # auto_disable | auto_enable | null
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["targets"] = [asdict(t) for t in self.targets]
        return d


def output(result: HookResult) -> None:
    """Write structured JSON to stdout (one line)."""
    d = result.to_dict()
    json.dump(d, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def today_str() -> str:
    return str(date.today())


def make_ok(hook_name: str) -> HookResult:
    """Convenience: produce an ok result with no targets."""
    return HookResult(
        hook=hook_name,
        timestamp=today_str(),
        status="ok",
        severity="low",
    )


def make_error(hook_name: str, error: str) -> HookResult:
    """Convenience: produce an error result."""
    return HookResult(
        hook=hook_name,
        timestamp=today_str(),
        status="error",
        severity="high",
        error_message=error,
    )
