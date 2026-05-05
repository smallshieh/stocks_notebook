import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from hook_runner import (
    apply_lifecycle_event,
    merge_existing_log,
    should_check_disabled_hook,
)


class HookRunnerTests(unittest.TestCase):
    def test_merge_existing_log_preserves_same_day_triggered_results(self):
        existing = {
            "triggered": [
                {"hook": "ma-breach-1210", "status": "alert", "severity": "high", "targets": []},
            ],
            "failed": [],
            "lifecycle_events": ["[auto_disable] ma-breach-2317"],
        }

        triggered, failed, skipped, lifecycle = merge_existing_log(
            existing=existing,
            triggered=[],
            failed=[],
            skipped=["ma-breach-1210", "deadline-2449"],
            lifecycle_events=[],
        )

        self.assertEqual([r["hook"] for r in triggered], ["ma-breach-1210"])
        self.assertEqual(failed, [])
        self.assertEqual(skipped, ["deadline-2449"])
        self.assertEqual(lifecycle, ["[auto_disable] ma-breach-2317"])

    def test_disabled_ma_hook_is_checked_for_auto_reenable(self):
        hook_def = {"lifecycle": {"auto_reenable_on": "ma20_breached"}}
        state = {
            "hooks": {
                "ma-breach-2317": {
                    "status": "disabled",
                    "disabled_reason": "auto_disable from script output",
                }
            }
        }

        self.assertTrue(should_check_disabled_hook("ma-breach-2317", hook_def, state))

    def test_auto_reenable_accepts_script_auto_disable_reason(self):
        hook_def = {"lifecycle": {"auto_reenable_on": "ma20_breached"}}
        state = {
            "hooks": {
                "ma-breach-2317": {
                    "status": "disabled",
                    "disabled_reason": "auto_disable from script output",
                }
            },
            "stocks": {},
        }
        result = {
            "targets": [
                {
                    "code": "2317",
                    "detail": {"breach_days": 1},
                }
            ]
        }

        apply_lifecycle_event("ma-breach-2317", result, hook_def, state)

        self.assertEqual(state["hooks"]["ma-breach-2317"]["status"], "active")
        self.assertNotIn("disabled_reason", state["hooks"]["ma-breach-2317"])
        self.assertEqual(state["stocks"]["2317"]["ma20_status"], "below")


if __name__ == "__main__":
    unittest.main()
