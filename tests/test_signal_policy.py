import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from signal_policy import evaluate_signal, infer_strategy_class, resolve_review_date


def metrics(**overrides):
    base = {
        "code": "0000",
        "current": 100.0,
        "ma20": 95.0,
        "ma_s": 0,
        "gbm_s": 0,
        "q_s": 0,
        "phys_s": 0,
        "total": 0,
        "volume_ratio": 1.0,
        "volume_label": "⚪ 平量",
    }
    base.update(overrides)
    return base


class SignalPolicyTests(unittest.TestCase):
    def test_growth_sell_zone_with_healthy_trend_is_extension_not_add(self):
        decision = evaluate_signal(
            metrics(ma_s=2, gbm_s=0, q_s=-2, phys_s=2, total=2),
            code="2330",
            strategy_class="growth_trend",
        )

        self.assertEqual(decision.action_group, "observe")
        self.assertEqual(decision.action_tag, "upside_growth_extension")
        self.assertIn("抱住不追高", decision.recommendation)

    def test_gbm_discount_does_not_cancel_bad_trend(self):
        decision = evaluate_signal(
            metrics(ma_s=-2, gbm_s=2, q_s=0, phys_s=0, total=0, current=100.0, ma20=90.0),
            code="2301",
            strategy_class="growth_trend",
        )

        self.assertEqual(decision.action_group, "observe")
        self.assertEqual(decision.action_tag, "downside_growth_discount_bad_trend")
        self.assertIn("GBM 低估不能抵銷趨勢轉弱", decision.reason)

    def test_dividend_anchor_negative_wave_never_sells_base_lot(self):
        decision = evaluate_signal(
            metrics(ma_s=-2, gbm_s=0, q_s=-2, phys_s=-2, total=-6, current=90.0, ma20=100.0),
            code="1215",
            strategy_class="dividend_anchor",
        )

        self.assertEqual(decision.action_group, "observe")
        self.assertNotEqual(decision.action_group, "defensive")
        self.assertIn("底倉", decision.recommendation)
        self.assertIn("底倉賣出需配息或基本面失效", decision.reason)

    def test_sell_zone_wave_minus_one_without_confirmation_is_observe(self):
        decision = evaluate_signal(
            metrics(ma_s=-1, gbm_s=0, q_s=-2, phys_s=2, total=-1, current=84.8, ma20=84.6),
            code="2546",
            strategy_class="growth_trend",
        )

        self.assertEqual(decision.action_group, "observe")
        self.assertEqual(decision.action_tag, "upside_growth_extension")
        self.assertIn("不用總分提前賣", decision.reason)

    def test_reversion_rolling_buy_zone_uses_quantile_as_primary_signal(self):
        decision = evaluate_signal(
            metrics(ma_s=0, gbm_s=0, q_s=2, phys_s=1, total=3),
            code="6488",
            strategy_class="reversion_rolling",
        )

        self.assertEqual(decision.action_group, "opportunity")
        self.assertEqual(decision.action_tag, "upside_rolling_buy_zone")
        self.assertIn("分位數買回區為主訊號", decision.reason)

    def test_hard_rules_override_signal_quality(self):
        decision = evaluate_signal(
            metrics(ma_s=2, gbm_s=0, q_s=0, phys_s=2, total=4),
            code="2330",
            strategy_class="growth_trend",
            hard_stop_triggered=True,
        )

        self.assertEqual(decision.action_group, "defensive")
        self.assertEqual(decision.action_tag, "downside_hard_rule")
        self.assertEqual(decision.signal_quality, "high")

    def test_dividend_cut_invalidates_anchor(self):
        decision = evaluate_signal(
            metrics(ma_s=2, gbm_s=0, q_s=0, phys_s=2, total=4),
            code="1215",
            strategy_class="dividend_anchor",
            dividend_cut=True,
        )

        self.assertEqual(decision.action_group, "defensive")
        self.assertIn("配息削減", decision.reason)

    def test_dividend_anchor_stop_loss_near_is_observe_not_sell(self):
        decision = evaluate_signal(
            metrics(ma_s=0, gbm_s=0, q_s=0, phys_s=0, total=0),
            code="1210",
            strategy_class="dividend_anchor",
            stop_loss_near=True,
        )

        self.assertEqual(decision.action_group, "observe")
        self.assertEqual(decision.action_tag, "downside_dividend_stop_near")
        self.assertIn("硬停損", decision.recommendation)

    def test_growth_quantile_break_is_defensive(self):
        decision = evaluate_signal(
            metrics(ma_s=0, gbm_s=0, q_s=-3, phys_s=0, total=-3),
            code="6239",
            strategy_class="growth_trend",
        )

        self.assertEqual(decision.action_group, "defensive")
        self.assertEqual(decision.action_tag, "downside_growth_break")

    def test_persistence_can_raise_quality(self):
        history = [
            {"action_tag": "downside_growth_distribution", "quality": "medium"},
            {"action_tag": "downside_growth_distribution", "quality": "medium"},
        ]
        decision = evaluate_signal(
            metrics(ma_s=-1, gbm_s=0, q_s=-2, phys_s=-1, total=-4, volume_ratio=1.6),
            code="2301",
            strategy_class="growth_trend",
            history=history,
        )

        self.assertEqual(decision.action_group, "defensive")
        self.assertEqual(decision.signal_quality, "high")
        self.assertGreaterEqual(decision.persistence_days, 3)

    def test_zero_prefixed_code_does_not_force_dividend_anchor(self):
        self.assertEqual(
            infer_strategy_class("0999", policies={}, trade_text=""),
            "growth_trend",
        )

    def test_review_date_resolves_cli_before_env(self):
        self.assertEqual(
            resolve_review_date("20260504", argv=[], env_var="__MISSING_ENV__"),
            "2026-05-04",
        )
        self.assertEqual(
            resolve_review_date(None, argv=["--date", "2026-05-04"], env_var="__MISSING_ENV__"),
            "2026-05-04",
        )


if __name__ == "__main__":
    unittest.main()
