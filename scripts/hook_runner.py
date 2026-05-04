"""
hook_runner.py — Unified hook execution engine.
================================================
Replaces the hook logic in daily-review steps 7.5 and 13.

Reads hooks.yaml → determines which hooks are due → executes scripts →
parses structured JSON output → updates hooks_state.json →
writes results to journals/logs/{TODAY}_hooks.json.

Usage:
    python scripts/hook_runner.py                    # normal run
    python scripts/hook_runner.py --dry-run          # preview only, no state changes
    python scripts/hook_runner.py --date 2026-05-04  # backdate (testing)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(BASE_DIR, ".agents", "hooks", "post-daily-review")
HOOKS_YAML = os.path.join(HOOKS_DIR, "hooks.yaml")
HOOKS_STATE_JSON = os.path.join(HOOKS_DIR, "hooks_state.json")
LOGS_DIR = os.path.join(BASE_DIR, "journals", "logs")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

SCRIPT_TIMEOUT_SECONDS = 120


def today_str() -> str:
    return str(date.today())


def trading_days_between(from_date: str, to_date: str) -> int:
    """Count Mon-Fri days strictly between from_date and to_date."""
    try:
        f = date.fromisoformat(from_date)
        t = date.fromisoformat(to_date)
    except (ValueError, TypeError):
        return 0
    count = 0
    current = f + timedelta(days=1)
    while current <= t:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def load_hooks_registry(path: str = HOOKS_YAML) -> dict[str, Any] | None:
    """Load hooks.yaml. Returns dict or None on failure."""
    if not os.path.exists(path):
        print(f"ERROR: hooks.yaml not found at {path}", file=sys.stderr)
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "hooks" not in data:
            print("ERROR: hooks.yaml missing 'hooks' key", file=sys.stderr)
            return None
        return data["hooks"]
    except ImportError:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: failed to parse hooks.yaml: {e}", file=sys.stderr)
        return None


def load_hooks_state(path: str = HOOKS_STATE_JSON) -> dict[str, Any]:
    """Load hooks_state.json or return empty default."""
    default = {"meta": {"last_run": None}, "hooks": {}, "stocks": {}}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        data.setdefault("meta", default["meta"])
        data.setdefault("hooks", default["hooks"])
        data.setdefault("stocks", default["stocks"])
        return data
    except Exception:
        return default


def save_hooks_state(state: dict[str, Any], path: str = HOOKS_STATE_JSON) -> None:
    """Persist hooks_state.json."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_hook_due(hook_name: str, hook_def: dict, state: dict, as_of: str) -> bool:
    """Check if a hook should execute today."""
    hook_state = state["hooks"].get(hook_name, {})
    status = hook_state.get("status", "active")
    if status != "active":
        return False

    trigger = hook_def.get("trigger", {})
    if trigger.get("type") != "schedule":
        return False

    n = trigger.get("every_n_trading_days", 1)
    last_run = hook_state.get("last_run")
    consecutive_failures = hook_state.get("consecutive_failures", 0)
    retry = hook_def.get("retry", {})
    max_fail = retry.get("max_consecutive_failures", 2)
    fallback_n = retry.get("fallback_frequency_days", 1)

    if consecutive_failures >= max_fail and max_fail > 0:
        effective_n = fallback_n
    else:
        effective_n = n

    if last_run is None or last_run == "" or last_run == "null":
        return True

    td = trading_days_between(last_run, as_of)
    return td >= effective_n


def execute_hook_script(script_cmd: str, timeout: int = SCRIPT_TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Run a hook script subprocess. Returns (exit_code, stdout, stderr)."""
    # Parse shell command into args list to avoid UNC path issue with cmd.exe
    parts = script_cmd.strip().split()
    if not parts:
        return -1, "", "empty command"

    # Resolve relative paths against BASE_DIR
    resolved_parts = []
    for p in parts:
        if '/' in p or '\\' in p:
            full = os.path.join(BASE_DIR, p.replace('/', os.sep))
            resolved_parts.append(os.path.normpath(full))
        else:
            resolved_parts.append(p)

    try:
        result = subprocess.run(
            resolved_parts,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=BASE_DIR,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def parse_hook_output(stdout: str) -> dict[str, Any] | None:
    """Parse a hook script's JSON stdout. Returns dict or None."""
    if not stdout:
        return None
    lines = [l.strip() for l in stdout.split("\n") if l.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def apply_lifecycle_event(hook_name: str, result: dict | None, hook_def: dict, state: dict) -> None:
    """Apply lifecycle changes from hook output or hooks_state.json signals."""
    hook_state = state["hooks"].setdefault(hook_name, {})
    lifecycle = hook_def.get("lifecycle", {})

    if result and result.get("lifecycle_event") == "auto_disable":
        hook_state["status"] = "disabled"
        hook_state["disabled_reason"] = "auto_disable from script output"
        return

    if result and result.get("lifecycle_event") == "auto_enable":
        hook_state["status"] = "active"
        hook_state.pop("disabled_reason", None)
        return

    auto_disable = lifecycle.get("auto_disable_on")
    if auto_disable == "ma20_recovered":
        for target in (result or {}).get("targets", []):
            detail = target.get("detail", {})
            code = str(target.get("code", ""))
            stock_state = state["stocks"].setdefault(code, {})
            if detail.get("ma20_recovered") or detail.get("current_price", 0) >= detail.get("ma20", 0):
                stock_state["ma20_status"] = "above"
                if _count_ma_below_targets(result) == 0:
                    hook_state["status"] = "disabled"
                    hook_state["disabled_reason"] = f"ma20_recovered auto-disable by hook_runner"

    auto_reenable = lifecycle.get("auto_reenable_on")
    if auto_reenable == "ma20_breached":
        for target in (result or {}).get("targets", []):
            code = str(target.get("code", ""))
            stock_state = state["stocks"].setdefault(code, {})
            detail = target.get("detail", {})
            if detail.get("breach_days", 0) >= 1:
                stock_state["ma20_status"] = "below"
                stock_state["ma20_breach_days"] = detail.get("breach_days", 0)
            if hook_state.get("status") == "disabled" and hook_state.get("disabled_reason", "").startswith("ma20_"):
                hook_state["status"] = "active"
                hook_state.pop("disabled_reason", None)

    permanent_disable = lifecycle.get("permanent_disable_on")
    if permanent_disable == "position_liquidated":
        for target in (result or {}).get("targets", []):
            detail = target.get("detail", {})
            if detail.get("position_liquidated"):
                hook_state["status"] = "disabled"
                hook_state["disabled_reason"] = "position_liquidated permanent"
                return
    if permanent_disable == "deadline_passed":
        for target in (result or {}).get("targets", []):
            detail = target.get("detail", {})
            if detail.get("deadline_passed"):
                hook_state["status"] = "disabled"
                hook_state["disabled_reason"] = "deadline_passed permanent"
                return


def _count_ma_below_targets(result: dict | None) -> int:
    """Count targets still below MA20."""
    if not result:
        return 0
    return sum(
        1 for t in result.get("targets", [])
        if t.get("detail", {}).get("current_price", 0) < t.get("detail", {}).get("ma20", 0)
    )


def format_results_summary(
    triggered: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    skipped: list[str],
    lifecycle_events: list[str],
    as_of: str,
) -> str:
    """Generate a Markdown summary of all hook results (for hooks JSON and journal)."""
    lines = [f"## Hook 執行摘要 ({as_of})", ""]

    high_items = [r for r in triggered if r.get("severity") == "high"]
    med_items = [r for r in triggered if r.get("severity") == "medium"]
    low_items = [r for r in triggered if r.get("severity") == "low"]

    if high_items:
        lines.append("### 🔴 高嚴重度")
        lines.append("| Hook | 標的 | 摘要 | 建議 |")
        lines.append("|------|------|------|------|")
        for r in high_items:
            for t in r.get("targets", []):
                lines.append(f"| {r['hook']} | {t.get('code','')} {t.get('name','')} | {t.get('summary','')} | {t.get('action','')} |")
        lines.append("")

    if med_items:
        lines.append("### 🟡 中嚴重度")
        lines.append("| Hook | 標的 | 摘要 | 建議 |")
        lines.append("|------|------|------|------|")
        for r in med_items:
            for t in r.get("targets", []):
                lines.append(f"| {r['hook']} | {t.get('code','')} {t.get('name','')} | {t.get('summary','')} | {t.get('action','')} |")
        lines.append("")

    if low_items:
        lines.append("### 🟢 正常")
        for r in low_items:
            lines.append(f"- **{r['hook']}**: {r.get('status', 'ok')}")
        lines.append("")

    if lifecycle_events:
        lines.append("### ⚙️ 生命週期事件")
        for ev in lifecycle_events:
            lines.append(f"- {ev}")
        lines.append("")

    if failed:
        lines.append("### ❌ 執行失敗")
        for f in failed:
            lines.append(f"- **{f['hook']}**: {f.get('error', '')}")
        lines.append("")

    if skipped:
        lines.append(f"### ⏭️ 跳過 ({len(skipped)} 個)")
        for s in skipped:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def run_hooks(as_of: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Main entry point. Returns comprehensive results dict."""
    as_of = as_of or today_str()
    registry = load_hooks_registry()
    if registry is None:
        return {"error": "hooks.yaml load failed", "triggered": [], "failed": []}

    state = load_hooks_state()
    state["meta"]["last_run"] = as_of

    triggered_results: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    skipped_hooks: list[str] = []
    lifecycle_events: list[str] = []
    all_targets: dict[str, list[dict]] = {}

    for hook_name, hook_def in registry.items():
        if not is_hook_due(hook_name, hook_def, state, as_of):
            skipped_hooks.append(hook_name)
            continue

        if dry_run:
            script = hook_def.get("script", "")
            print(f"[DRY-RUN] {hook_name}: would execute: {script}")
            triggered_results.append({
                "hook": hook_name,
                "severity": hook_def.get("severity_default", "low"),
                "dry_run": True,
                "targets": [],
                "status": "ok",
            })
            continue

        script = hook_def.get("script", "")
        if not script:
            failed_results.append({"hook": hook_name, "error": "no script defined"})
            continue

        exit_code, stdout_text, stderr_text = execute_hook_script(script)
        hook_state = state["hooks"].setdefault(hook_name, {})

        if exit_code != 0:
            hook_state["consecutive_failures"] = hook_state.get("consecutive_failures", 0) + 1
            error_msg = stderr_text or stdout_text or f"exit code {exit_code}"
            failed_results.append({"hook": hook_name, "error": error_msg})
            print(f"  ❌ {hook_name}: {error_msg}")
            save_hooks_state(state)
            continue

        parsed = parse_hook_output(stdout_text)
        if parsed is None:
            hook_state["consecutive_failures"] = hook_state.get("consecutive_failures", 0) + 1
            failed_results.append({"hook": hook_name, "error": f"invalid JSON output: {stdout_text[:200]}"})
            print(f"  ❌ {hook_name}: invalid JSON")
            save_hooks_state(state)
            continue

        hook_state["last_run"] = as_of
        hook_state["run_count"] = hook_state.get("run_count", 0) + 1
        hook_state["consecutive_failures"] = 0
        hook_state["last_result"] = {
            "status": parsed.get("status"),
            "severity": parsed.get("severity"),
            "summary": "; ".join(t.get("summary", "") for t in parsed.get("targets", [])),
        }

        apply_lifecycle_event(hook_name, parsed, hook_def, state)
        lc = parsed.get("lifecycle_event")
        if lc:
            lifecycle_events.append(f"[{lc}] {hook_name}")
        new_status = state["hooks"][hook_name].get("status")
        if new_status and new_status != hook_state.get("status", "active"):
            lifecycle_events.append(f"[status → {new_status}] {hook_name}")

        triggered_results.append(parsed)

        severity = parsed.get("severity", hook_def.get("severity_default", "low"))
        print(f"  {'🔴' if severity == 'high' else '🟡' if severity == 'medium' else '🟢'} {hook_name}: {parsed.get('status')}")

        for target in parsed.get("targets", []):
            code = str(target.get("code", ""))
            all_targets.setdefault(code, []).append(target)

        save_hooks_state(state)

    summary = format_results_summary(triggered_results, failed_results, skipped_hooks, lifecycle_events, as_of)

    output_log_path = os.path.join(LOGS_DIR, f"{as_of}_hooks.json")
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_data = {
        "date": as_of,
        "dry_run": dry_run,
        "triggered": triggered_results,
        "failed": failed_results,
        "skipped": skipped_hooks,
        "lifecycle_events": lifecycle_events,
        "summary_md": summary,
    }
    with open(output_log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return {
        "as_of": as_of,
        "dry_run": dry_run,
        "triggered_count": len(triggered_results),
        "failed_count": len(failed_results),
        "skipped_count": len(skipped_hooks),
        "high_severity_targets": [
            t for r in triggered_results
            if r.get("severity") == "high"
            for t in r.get("targets", [])
        ],
        "lifecycle_events": lifecycle_events,
        "summary_md": summary,
        "output_log": output_log_path,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hook execution engine")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing or writing state")
    parser.add_argument("--date", dest="as_of", default=None, help="Override date (YYYY-MM-DD)")
    parser.add_argument("--summary-only", action="store_true", help="Print only summary to stdout")
    args = parser.parse_args()

    # Ensure scripts directory on path so hook scripts can import hook_output
    sys.path.insert(0, SCRIPTS_DIR)

    result = run_hooks(as_of=args.as_of, dry_run=args.dry_run)

    if args.summary_only:
        print(result.get("summary_md", ""))
    else:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would trigger {result['triggered_count']} hooks, skip {result['skipped_count']}")
        else:
            print(f"\n✅ {result['triggered_count']} triggered, {result['failed_count']} failed, {result['skipped_count']} skipped")
            if result.get("high_severity_targets"):
                print("⚠️  High-severity targets identified. Review journals/logs/")
            lc = result.get("lifecycle_events", [])
            if lc:
                print("⚙️  Lifecycle events:")
                for ev in lc:
                    print(f"   {ev}")
            print(f"📄 Full log: {result.get('output_log')}")
