"""
migrate_hooks.py — One-time migration from old hook state to hooks_state.json.
================================================================================
Reads:
  - .agents/hooks/post-daily-review/_state.json     (old hook schedule state)
  - journals/logs/signal_state.json                  (old structured signal state)

Writes:
  - .agents/hooks/post-daily-review/hooks_state.json (new unified state)

Usage:
  python scripts/migrate_hooks.py            # migrate, keep backups
  python scripts/migrate_hooks.py --dry-run  # preview only
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(BASE_DIR, ".agents", "hooks", "post-daily-review")
OLD_STATE = os.path.join(HOOKS_DIR, "_state.json")
OLD_SIGNAL = os.path.join(BASE_DIR, "journals", "logs", "signal_state.json")
NEW_STATE = os.path.join(HOOKS_DIR, "hooks_state.json")


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def migrate(dry_run: bool = False) -> dict:
    old_hooks = load_json(OLD_STATE)
    old_signals = load_json(OLD_SIGNAL)

    new_state = {
        "meta": {
            "last_run": str(date.today()),
            "migrated_from": {
                "_state.json": OLD_STATE,
                "signal_state.json": OLD_SIGNAL if os.path.exists(OLD_SIGNAL) else None,
            },
        },
        "hooks": {},
        "stocks": {},
    }

    for hook_name, hook_data in old_hooks.items():
        new_state["hooks"][hook_name] = {
            "status": "active",
            "last_run": hook_data.get("last_run"),
            "run_count": hook_data.get("run_count", 0),
            "consecutive_failures": 0,
            "last_result": None,
        }

    for code, entries in old_signals.get("signals", {}).items():
        code_str = str(code)
        if not entries:
            continue
        latest = entries[-1] if isinstance(entries, list) else entries
        wave = latest.get("wave_components", {}) if isinstance(latest, dict) else {}
        new_state["stocks"][code_str] = {
            "wave_score": wave.get("total", 0),
            "wave_components": {
                "ma": wave.get("ma", 0),
                "gbm": wave.get("gbm", 0),
                "quantile": wave.get("quantile", 0),
                "physics": wave.get("physics", 0),
            },
            "signal_quality": latest.get("quality") if isinstance(latest, dict) else None,
            "position_status": "holding",
        }

    if not dry_run:
        # Backup old files
        for old_path in [OLD_STATE, OLD_SIGNAL]:
            if os.path.exists(old_path):
                backup = old_path + ".bak"
                shutil.copy2(old_path, backup)

        os.makedirs(os.path.dirname(NEW_STATE), exist_ok=True)
        with open(NEW_STATE, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=2)

    return new_state


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = migrate(dry_run=dry)

    print(f"Migrated {len(result['hooks'])} hooks + {len(result['stocks'])} stocks")
    if dry:
        print("[DRY-RUN] No files written")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"State written to {NEW_STATE}")
        print(f"Backups: {OLD_STATE}.bak, {OLD_SIGNAL}.bak" if os.path.exists(OLD_SIGNAL) else f"Backup: {OLD_STATE}.bak")
