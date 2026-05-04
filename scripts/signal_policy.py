"""
signal_policy.py — Unified signal diagnosis and decision routing.

The Wave total remains a summary metric. Trading actions are derived from:
  1. hard rules supplied by the caller,
  2. position strategy class,
  3. component-level diagnosis and signal quality,
  4. Wave total only as supporting context.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITION_POLICY_CSV = os.path.join(BASE_DIR, "capital", "position_policy.csv")
SIGNAL_STATE_JSON = os.path.join(BASE_DIR, "journals", "logs", "signal_state.json")

STRATEGY_LABELS = {
    "growth_trend": "📈 成長趨勢",
    "dividend_anchor": "💰 殖利率錨定",
    "reversion_rolling": "🔄 區間滾動",
}

QUALITY_LABELS = {
    "high": "🟢 高",
    "medium": "🟡 中",
    "low": "🔴 低",
}


@dataclass
class SignalDecision:
    code: str
    strategy_class: str
    strategy_label: str
    action_group: str
    action_priority: int
    action_tag: str
    action_label: str
    recommendation: str
    reason: str
    signal_quality: str
    signal_quality_label: str
    quality_score: int
    trend_label: str
    gbm_label: str
    position_label: str
    energy_label: str
    volume_label: str
    persistence_days: int


def load_position_policies(path: str = POSITION_POLICY_CSV) -> dict[str, dict[str, str]]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return {
            row["code"].strip(): {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
            if row.get("code")
        }


def infer_strategy_class(
    code: str,
    *,
    trade_text: str = "",
    policies: dict[str, dict[str, str]] | None = None,
) -> str:
    policies = policies or load_position_policies()
    policy = policies.get(str(code))
    if policy and policy.get("strategy_class"):
        return policy["strategy_class"]

    text = trade_text or ""
    if any(token in text for token in ("殖利率錨定", "配息防禦", "股息複利", "高股息", "ETF")):
        return "dividend_anchor"
    if any(token in text for token in ("零股滾動", "買回區", "操作倉", "回測買點")):
        return "reversion_rolling"
    return "growth_trend"


def strategy_label(strategy_class: str) -> str:
    return STRATEGY_LABELS.get(strategy_class, strategy_class)


def load_signal_state(path: str = SIGNAL_STATE_JSON) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"signals": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("signals"), dict):
            return data
    except Exception:
        pass
    return {"signals": {}}


def save_signal_state(state: dict[str, Any], path: str = SIGNAL_STATE_JSON) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def recent_entries(state: dict[str, Any], code: str, limit: int = 5) -> list[dict[str, Any]]:
    entries = state.get("signals", {}).get(str(code), [])
    if not isinstance(entries, list):
        return []
    return entries[-limit:]


def record_signal_state(
    state: dict[str, Any],
    *,
    code: str,
    as_of: str,
    source: str,
    metrics: dict[str, Any],
    decision: SignalDecision,
    keep: int = 20,
) -> None:
    signals = state.setdefault("signals", {})
    entries = signals.setdefault(str(code), [])
    entry = {
        "date": str(as_of),
        "source": source,
        "strategy_class": decision.strategy_class,
        "wave_components": {
            "ma": int(metrics.get("ma_s", 0)),
            "gbm": int(metrics.get("gbm_s", 0)),
            "quantile": int(metrics.get("q_s", 0)),
            "physics": int(metrics.get("phys_s", 0)),
            "total": int(metrics.get("total", 0)),
        },
        "quality": decision.signal_quality,
        "action_tag": decision.action_tag,
    }
    entries = [
        e for e in entries
        if not (e.get("date") == entry["date"] and e.get("source") == source)
    ]
    entries.append(entry)
    signals[str(code)] = entries[-keep:]


def compute_volume_metrics(df: Any) -> dict[str, Any]:
    try:
        volume = df["Volume"].dropna()
        if len(volume) < 2:
            raise ValueError("not enough volume rows")
        today_vol = float(volume.iloc[-1])
        avg5 = float(volume.tail(6).iloc[:-1].mean()) if len(volume) >= 6 else float(volume.tail(5).mean())
        avg20 = float(volume.tail(21).iloc[:-1].mean()) if len(volume) >= 21 else float(volume.tail(20).mean())
        ratio5 = today_vol / avg5 if avg5 else 0.0
        ratio20 = today_vol / avg20 if avg20 else 0.0
    except Exception:
        return {
            "today_volume": None,
            "avg5_volume": None,
            "avg20_volume": None,
            "volume_ratio": None,
            "volume_ratio20": None,
            "volume_label": "⚪ 量能未知",
        }

    if ratio5 >= 1.5:
        label = "🔴 爆量"
    elif ratio5 < 0.8:
        label = "🔵 縮量"
    else:
        label = "⚪ 平量"
    return {
        "today_volume": today_vol,
        "avg5_volume": avg5,
        "avg20_volume": avg20,
        "volume_ratio": ratio5,
        "volume_ratio20": ratio20,
        "volume_label": label,
    }


def diagnose_components(metrics: dict[str, Any]) -> dict[str, str]:
    ma = int(metrics.get("ma_s", 0))
    gbm = int(metrics.get("gbm_s", 0))
    q = int(metrics.get("q_s", 0))
    phys = int(metrics.get("phys_s", 0))

    if ma >= 1:
        trend = "趨勢向上"
    elif ma <= -1:
        trend = "趨勢轉弱"
    else:
        trend = "趨勢混合"

    if gbm >= 2:
        gbm_label = "模型低估"
    elif gbm <= -2:
        gbm_label = "模型偏熱"
    elif gbm == -1:
        gbm_label = "略高於期望"
    else:
        gbm_label = "期望合理"

    if q <= -3:
        position = "跌破暫停線"
    elif q == -2:
        position = "賣出區"
    elif q >= 2:
        position = "買回區"
    else:
        position = "合理區"

    if phys >= 1:
        energy = "動能健康"
    elif phys <= -1:
        energy = "動能轉弱"
    else:
        energy = "動能混合"

    return {
        "trend_label": trend,
        "gbm_label": gbm_label,
        "position_label": position,
        "energy_label": energy,
    }


def _same_direction_count(history: list[dict[str, Any]], direction: str) -> int:
    if not direction:
        return 1
    count = 1
    for entry in reversed(history):
        tag = str(entry.get("action_tag", ""))
        if tag.startswith(direction):
            count += 1
        else:
            break
    return count


def _quality(metrics: dict[str, Any], history: list[dict[str, Any]], direction: str) -> tuple[str, int, int]:
    ma = int(metrics.get("ma_s", 0))
    q = int(metrics.get("q_s", 0))
    phys = int(metrics.get("phys_s", 0))
    volume_ratio = metrics.get("volume_ratio")
    persistence = _same_direction_count(history, direction)

    score = 0
    if direction == "downside":
        if q <= -2 or float(metrics.get("current", 0)) < float(metrics.get("ma20", 0)):
            score += 1
        if ma <= -1:
            score += 1
        if phys <= -1:
            score += 1
    elif direction == "upside":
        if q >= 2 or ma >= 1:
            score += 1
        if ma >= 0:
            score += 1
        if phys >= 1:
            score += 1

    if isinstance(volume_ratio, (int, float)) and volume_ratio >= 1.5:
        score += 1
    if persistence >= 2:
        score += 1

    if score >= 4:
        return "high", score, persistence
    if score >= 2:
        return "medium", score, persistence
    return "low", score, persistence


def _decision(
    *,
    code: str,
    strategy_class: str,
    action_group: str,
    action_priority: int,
    action_tag: str,
    action_label: str,
    recommendation: str,
    reason: str,
    quality: str,
    quality_score: int,
    persistence_days: int,
    diagnosis: dict[str, str],
    metrics: dict[str, Any],
) -> SignalDecision:
    return SignalDecision(
        code=str(code),
        strategy_class=strategy_class,
        strategy_label=strategy_label(strategy_class),
        action_group=action_group,
        action_priority=action_priority,
        action_tag=action_tag,
        action_label=action_label,
        recommendation=recommendation,
        reason=reason,
        signal_quality=quality,
        signal_quality_label=QUALITY_LABELS.get(quality, quality),
        quality_score=quality_score,
        trend_label=diagnosis["trend_label"],
        gbm_label=diagnosis["gbm_label"],
        position_label=diagnosis["position_label"],
        energy_label=diagnosis["energy_label"],
        volume_label=str(metrics.get("volume_label") or "⚪ 量能未知"),
        persistence_days=persistence_days,
    )


def evaluate_signal(
    metrics: dict[str, Any],
    *,
    code: str | None = None,
    strategy_class: str | None = None,
    policies: dict[str, dict[str, str]] | None = None,
    trade_text: str = "",
    history: list[dict[str, Any]] | None = None,
    hard_stop_triggered: bool = False,
    stop_loss_near: bool = False,
    thesis_broken: bool = False,
    dividend_cut: bool = False,
) -> SignalDecision:
    code = str(code or metrics.get("code", ""))
    strategy_class = strategy_class or infer_strategy_class(code, trade_text=trade_text, policies=policies)
    history = history or []
    diagnosis = diagnose_components(metrics)

    ma = int(metrics.get("ma_s", 0))
    q = int(metrics.get("q_s", 0))
    phys = int(metrics.get("phys_s", 0))
    current = float(metrics.get("current", 0) or 0)
    ma20 = float(metrics.get("ma20", 0) or 0)
    below_ma20 = bool(ma20 and current < ma20)

    if hard_stop_triggered or thesis_broken or dividend_cut:
        reason = "硬規則觸發"
        if thesis_broken:
            reason = "論點失效"
        elif dividend_cut:
            reason = "配息削減，殖利率錨定失效"
        quality, score, persistence = "high", 5, 1
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="defensive", action_priority=0, action_tag="downside_hard_rule",
            action_label="🔴 硬規則處理", recommendation="硬規則處理",
            reason=reason, quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )

    if strategy_class == "dividend_anchor":
        if stop_loss_near:
            quality, score, persistence = "medium", 3, 1
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="observe", action_priority=2, action_tag="downside_dividend_stop_near",
                action_label="🟡 硬停損接近", recommendation="檢查硬停損",
                reason="殖利率底倉仍需尊重硬停損線", quality=quality,
                quality_score=score, persistence_days=persistence, diagnosis=diagnosis, metrics=metrics,
            )
        if below_ma20 or ma <= -1 or q <= -2:
            quality, score, persistence = _quality(metrics, history, "downside")
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="observe", action_priority=2, action_tag="downside_dividend_observe",
                action_label="🟡 底倉不因 Wave 賣出", recommendation="底倉依殖利率；波段倉觀察",
                reason="月線/Wave 只影響波段倉與加碼節奏，底倉賣出需配息或基本面失效",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        if q >= 2:
            quality, score, persistence = _quality(metrics, history, "upside")
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="opportunity", action_priority=1, action_tag="upside_dividend_value_check",
                action_label="🟢 檢查殖利率加碼", recommendation="檢查殖利率門檻",
                reason="價格位置偏低，但加碼仍以殖利率門檻與 Core 配置為準",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="normal", action_priority=3, action_tag="neutral_dividend_hold",
            action_label="✅ 底倉持有", recommendation="底倉持有",
            reason="殖利率錨定股未觸發硬規則", quality="low", quality_score=0,
            persistence_days=1, diagnosis=diagnosis, metrics=metrics,
        )

    if strategy_class == "reversion_rolling":
        if q <= -3:
            quality, score, persistence = _quality(metrics, history, "downside")
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="defensive", action_priority=0, action_tag="downside_rolling_break",
                action_label="🔴 區間破壞", recommendation="暫停滾動/檢查停損",
                reason="分位數跌破暫停線，區間策略失效風險升高",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        if q >= 2:
            quality, score, persistence = _quality(metrics, history, "upside")
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="opportunity", action_priority=1, action_tag="upside_rolling_buy_zone",
                action_label="🟢 買回區", recommendation="依回測區評估買回",
                reason="區間滾動以分位數買回區為主訊號，MA/物理只做確認",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        if q == -2:
            direction = "downside" if phys <= -1 else "upside"
            quality, score, persistence = _quality(metrics, history, direction)
            label = "🔴 區間賣出確認" if phys <= -1 and quality != "low" else "🟡 賣出區觀察"
            group = "defensive" if phys <= -1 and quality != "low" else "observe"
            priority = 0 if group == "defensive" else 2
            tag = "downside_rolling_sell_zone" if group == "defensive" else "upside_rolling_extension"
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group=group, action_priority=priority, action_tag=tag,
                action_label=label,
                recommendation="賣出區處理" if group == "defensive" else "賣出區觀察",
                reason="區間策略以分位數為主；需動能轉弱才升級賣出",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="normal", action_priority=3, action_tag="neutral_rolling_wait",
            action_label="✅ 區間等待", recommendation="區間等待",
            reason="未進入買回區或賣出確認區", quality="low", quality_score=0,
            persistence_days=1, diagnosis=diagnosis, metrics=metrics,
        )

    # growth_trend
    if q <= -3:
        quality, score, persistence = _quality(metrics, history, "downside")
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="defensive", action_priority=0, action_tag="downside_growth_break",
            action_label="🔴 波段破壞", recommendation="防守處理",
            reason="跌破暫停線，價格位置已非一般回檔",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    if q == -2:
        quality, score, persistence = _quality(metrics, history, "downside")
        if (phys <= -1 or (below_ma20 and ma <= -1)) and quality != "low":
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="defensive", action_priority=0, action_tag="downside_growth_distribution",
                action_label="🔴 高位轉弱確認", recommendation="依 SOP 減碼",
                reason="賣出區疊加趨勢/動能轉弱，訊號已有確認",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="observe", action_priority=2, action_tag="upside_growth_extension",
            action_label="🟡 趨勢延伸", recommendation="抱住不追高",
            reason="賣出區但未見足夠轉弱確認，不用總分提前賣",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    if below_ma20 and (ma <= -1 or phys <= -1):
        quality, score, persistence = _quality(metrics, history, "downside")
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="observe", action_priority=2, action_tag="downside_growth_ma_watch",
            action_label="🟡 趨勢防守觀察", recommendation="觀察/等確認",
            reason="跌破月線但未達波段破壞，需持續性或量能確認",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    if q >= 2:
        quality, score, persistence = _quality(metrics, history, "upside")
        if ma >= 0 and phys >= 0:
            return _decision(
                code=code, strategy_class=strategy_class,
                action_group="opportunity", action_priority=1, action_tag="upside_growth_pullback",
                action_label="🟢 回測買點確認", recommendation="可依計畫加碼",
                reason="回測買點疊加趨勢未壞，符合成長趨勢股加碼條件",
                quality=quality, quality_score=score, persistence_days=persistence,
                diagnosis=diagnosis, metrics=metrics,
            )
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="observe", action_priority=2, action_tag="upside_growth_falling_knife",
            action_label="🟡 便宜但趨勢壞", recommendation="等止跌確認",
            reason="位置便宜但趨勢/動能未確認，避免 falling knife",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    if ma >= 1 and phys >= 1:
        quality, score, persistence = _quality(metrics, history, "upside")
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="observe", action_priority=2, action_tag="upside_growth_healthy",
            action_label="🟡 趨勢健康", recommendation="持有觀察",
            reason="趨勢與動能健康，但未進入買回區，不用因總分追價",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    if ma <= -1 and int(metrics.get("gbm_s", 0)) >= 2:
        quality, score, persistence = _quality(metrics, history, "downside")
        return _decision(
            code=code, strategy_class=strategy_class,
            action_group="observe", action_priority=2, action_tag="downside_growth_discount_bad_trend",
            action_label="🟡 低估但趨勢壞", recommendation="等趨勢修復",
            reason="GBM 低估不能抵銷趨勢轉弱",
            quality=quality, quality_score=score, persistence_days=persistence,
            diagnosis=diagnosis, metrics=metrics,
        )
    return _decision(
        code=code, strategy_class=strategy_class,
        action_group="normal", action_priority=3, action_tag="neutral_growth_hold",
        action_label="✅ 無明確動作", recommendation="持有/等待",
        reason="四維診斷未形成可執行訊號", quality="low", quality_score=0,
        persistence_days=1, diagnosis=diagnosis, metrics=metrics,
    )


def decision_to_dict(decision: SignalDecision) -> dict[str, Any]:
    return asdict(decision)


def normalize_review_date(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return str(date.today())
    raw = raw.replace("/", "-")
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"日期格式錯誤：{value!r}，請用 YYYY-MM-DD 或 YYYYMMDD") from exc


def resolve_review_date(
    cli_date: str | None = None,
    *,
    env_var: str = "REVIEW_DATE",
    argv: list[str] | None = None,
) -> str:
    """Resolve the intended after-market review date.

    Priority: explicit CLI value > REVIEW_DATE env var > --date/--review-date in argv > today.
    """
    raw = cli_date or os.environ.get(env_var)
    args = sys.argv[1:] if argv is None else argv
    if not raw:
        for i, arg in enumerate(args):
            if arg.startswith("--date="):
                raw = arg.split("=", 1)[1]
                break
            if arg.startswith("--review-date="):
                raw = arg.split("=", 1)[1]
                break
            if arg in ("--date", "--review-date") and i + 1 < len(args):
                raw = args[i + 1]
                break
    return normalize_review_date(raw)


def today_str() -> str:
    return resolve_review_date()


def extract_code_from_path(path: str) -> str | None:
    m = re.match(r"^(\d[\dA-Za-z]{3,5})", os.path.basename(path))
    return m.group(1) if m else None
