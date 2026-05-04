"""
watchlist_scan.py — 候補股自動掃描
每次執行會：
  1. 讀取 /watchlist 下所有 MD 檔
  2. 抓取現價、20MA（月線）、60MA（季線）
  3. 評估可量化的買入觸發條件
  4. 若今天尚未記錄，自動在 MD 的「每月更新紀錄」新增一行
  5. 對有 N 計畫的標的：計算 Wave Score，檢查 zone/above_consec 進場條件
  6. 觸發時輸出 ⚠️ 並寫入 scripts/_entry_alerts.json（7 天滾動視窗）

用法：
  python scripts/watchlist_scan.py
  python scripts/watchlist_scan.py --date 2026-05-04
"""

import os
import re
import sys
import json
import time
import datetime
import yfinance as yf
import pandas as pd
import numpy as np
from curl_cffi import requests as creq

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from quantile_engine import compute_quantile_metrics
    from physics_engine import compute_physics, detect_antigravity, detect_energy_dissipation
    from signal_policy import (
        compute_volume_metrics,
        evaluate_signal,
        load_position_policies,
        load_signal_state,
        recent_entries,
        record_signal_state,
        resolve_review_date,
        save_signal_state,
    )
    _ENGINES_AVAILABLE = True
except ImportError:
    _ENGINES_AVAILABLE = False

_CURL_SESSION = creq.Session(verify=False, impersonate='chrome')

import warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

WATCHLIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'watchlist')
SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
TODAY = resolve_review_date() if _ENGINES_AVAILABLE else datetime.date.today().strftime("%Y-%m-%d")

# 載入 N 計畫進場條件
_PLANS_PATH = os.path.join(SCRIPTS_DIR, 'watchlist_entry_plans.json')
try:
    with open(_PLANS_PATH, 'r', encoding='utf-8') as _f:
        ENTRY_PLANS = {k: v for k, v in json.load(_f).items() if not k.startswith('_')}
except Exception:
    ENTRY_PLANS = {}

# ── 可量化的觸發條件定義 ──────────────────────────────────────────────────────
QUANT_TRIGGERS = [
    (
        "股價回測月線支撐",
        lambda p, m20, m60: (
            1.0 <= p / m20 <= 1.03,
            f"現價 {p:.1f} 距月線 {m20:.1f} 僅 {(p/m20-1)*100:.1f}%（月線回測中）"
        )
    ),
    (
        "股價跌至月線下方",
        lambda p, m20, m60: (
            p < m20,
            f"現價 {p:.1f} 跌破月線 {m20:.1f}（需觀察是否企穩）"
        )
    ),
    (
        "股價突破季線",
        lambda p, m20, m60: (
            p > m60,
            f"現價 {p:.1f} 站上季線 {m60:.1f}（+{(p/m60-1)*100:.1f}%）"
        )
    ),
    (
        "股價跌近季線支撐",
        lambda p, m20, m60: (
            1.0 <= p / m60 <= 1.05,
            f"現價 {p:.1f} 距季線 {m60:.1f} 僅 {(p/m60-1)*100:.1f}%（季線回測）"
        )
    ),
]


def get_market_data(code: str, retries=3, delay=5):
    """取得現價、20MA、60MA、完整 hist DataFrame；TW/TWO 自動切換，含重試。"""
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                hist = yf.Ticker(f"{code}{suffix}", session=_CURL_SESSION).history(period="6mo", auto_adjust=False)
                if hist is not None and not hist.empty:
                    hist.columns = [c.title() for c in hist.columns]
                    close = hist['Close'].dropna()
                    price = float(close.iloc[-1])
                    ma20  = float(close.rolling(20, min_periods=1).mean().iloc[-1])
                    ma60  = float(close.rolling(60, min_periods=1).mean().iloc[-1])
                    return price, ma20, ma60, hist
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None, None, None, None


def compute_wave_snapshot_silent(code: str, hist: pd.DataFrame) -> dict | None:
    """
    靜默計算 Wave 四維診斷資料，不輸出任何文字。
    引擎不可用或計算失敗時回傳 None。
    """
    if not _ENGINES_AVAILABLE:
        return None
    try:
        prices = hist['Close'].dropna()
        current = float(prices.iloc[-1])

        # 1. 均線結構 (-2 ~ +2)
        ma5  = float(prices.tail(5).mean())
        ma10 = float(prices.tail(10).mean())
        ma20 = float(prices.tail(20).mean())
        ma60 = float(prices.tail(60).mean())
        ma_raw   = sum([current > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60])
        ma_score = ma_raw - 2

        # 2. GBM σ 位置 (-2 ~ +2)
        log_returns = np.diff(np.log(prices.values))
        try:
            from arch import arch_model
            am  = arch_model(log_returns * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
            res = am.fit(disp='off')
            sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
        except Exception:
            sigma = float(np.std(log_returns, ddof=1)) * np.sqrt(252)
        mu_daily = float(np.mean(log_returns))
        mu = (mu_daily + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252

        T   = 20 / 252
        E   = current * np.exp(mu * T)
        std = sigma * np.sqrt(T) * current
        if current < E - 0.5 * std:
            gbm_score = 2
        elif current <= E + 0.5 * std:
            gbm_score = 0
        elif current <= E + std:
            gbm_score = -1
        else:
            gbm_score = -2

        # 3. 分位數 (-3 ~ +3)
        q = compute_quantile_metrics(hist)
        if current >= q['sell_low']:
            q_score = -2
        elif current >= q['buy_high']:
            q_score = 0
        elif current >= q['buy_low']:
            q_score = 2
        elif current >= q['deep_low']:
            q_score = 3
        else:
            q_score = -3

        # 4. 物理引擎 (-2 ~ +2)
        phys_df   = compute_physics(hist)
        latest    = phys_df.iloc[-1]
        momentum  = latest.get('momentum', 0) or 0
        reynolds  = latest.get('reynolds', 0) or 0
        antigrav  = detect_antigravity(phys_df)
        ener_diss = detect_energy_dissipation(phys_df)
        phys_raw  = sum([momentum > 0, reynolds < 2000, not antigrav, not ener_diss])
        phys_score = phys_raw - 2

        volume = compute_volume_metrics(hist)
        return {
            'code': code,
            'current': current,
            'ma20': ma20,
            'ma_s': ma_score,
            'gbm_s': gbm_score,
            'q_s': q_score,
            'phys_s': phys_score,
            'total': ma_score + gbm_score + q_score + phys_score,
            **volume,
        }
    except Exception:
        return None


def policy_allows_entry(decision) -> bool:
    if decision is None:
        return False
    if decision.signal_quality == 'low':
        return False
    return decision.action_tag in {
        'upside_growth_pullback',
        'upside_growth_healthy',
        'upside_rolling_buy_zone',
        'upside_dividend_value_check',
    }


def check_n_plan_conditions(code: str, price: float, hist: pd.DataFrame,
                             wave_score: int, plan: dict, decision=None) -> list:
    """
    檢查 N 計畫進場條件，回傳已觸發條件列表。
    每個 item: {label, description, action, wave_score, price}
    """
    triggered = []
    closes = hist['Close'].dropna()

    for cond in plan.get('conditions', []):
        label      = cond.get('label', '?')
        ctype      = cond.get('type', '')
        wave_min   = cond.get('wave_min', 0)
        desc       = cond.get('description', '')
        action     = cond.get('action', '')

        if ctype == 'zone':
            pmin = cond['price_min']
            pmax = cond['price_max']
            if pmin <= price <= pmax and wave_score >= wave_min and policy_allows_entry(decision):
                triggered.append({
                    'label': label, 'description': desc,
                    'action': action, 'wave_score': wave_score, 'price': price,
                    'policy': decision.recommendation if decision else '',
                })

        elif ctype == 'above_consec':
            threshold   = cond['price_threshold']
            range_max   = cond.get('price_range_max', float('inf'))
            consecutive = cond.get('consecutive', 2)
            recent = closes.iloc[-consecutive:]
            if (len(recent) >= consecutive
                    and bool((recent >= threshold).all())
                    and bool((recent <= range_max).all())
                    and wave_score >= wave_min
                    and policy_allows_entry(decision)):
                triggered.append({
                    'label': label, 'description': desc,
                    'action': action, 'wave_score': wave_score, 'price': price,
                    'policy': decision.recommendation if decision else '',
                })

    return triggered


def save_entry_alerts(new_alerts: list):
    """
    將 N 計畫觸發寫入 _entry_alerts.json（7 天滾動視窗）。
    同日同標的同 label 的重複警示不重複追加。
    """
    path = os.path.join(SCRIPTS_DIR, '_entry_alerts.json')
    existing = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cutoff = (datetime.date.fromisoformat(TODAY) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            existing = [
                a for a in data.get('alerts', [])
                if a.get('triggered_at', '') >= cutoff
            ]
        except Exception:
            pass

    existing_keys = {
        (a['code'], a['condition_label'], a['triggered_at'])
        for a in existing
    }

    for a in new_alerts:
        key = (a['code'], a['condition_label'], TODAY)
        if key not in existing_keys:
            clean = {**a, 'wave_score': int(a['wave_score']), 'price': float(a['price'])}
            existing.append(dict(clean, triggered_at=TODAY))
            existing_keys.add(key)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'scan_date': TODAY, 'alerts': existing}, f, ensure_ascii=False, indent=2)


def evaluate_triggers(price, ma20, ma60):
    """跑所有可量化條件，回傳觸發清單。"""
    fired = []
    for name, fn in QUANT_TRIGGERS:
        triggered, detail = fn(price, ma20, ma60)
        if triggered:
            fired.append(f"{name}：{detail}")
    return fired


def build_status_text(price, ma20, ma60, fired_triggers):
    """產生寫入 MD 的狀態更新文字。"""
    ma20_pct = (price / ma20 - 1) * 100
    ma60_pct = (price / ma60 - 1) * 100
    base = (f"現價 {price:.1f}，月線 {ma20:.1f}（{ma20_pct:+.1f}%），"
            f"季線 {ma60:.1f}（{ma60_pct:+.1f}%）")
    if fired_triggers:
        trigger_str = "；".join(fired_triggers)
        return f"{base}。⚡ 觸發：{trigger_str}"
    return f"{base}。無量化觸發訊號"


def append_today_record(filepath: str, price: float, ma20: float, ma60: float,
                        fired_triggers: list):
    """若今天尚未記錄，在 MD 的每月更新紀錄 table 末尾插入新行。"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if TODAY in content:
        return False

    status = build_status_text(price, ma20, ma60, fired_triggers)
    new_row = f"| {TODAY} | **{price:.2f}** 元 | {status} |"

    table_pattern = re.compile(
        r'(## 每月更新紀錄.*?(?:\n\|[^\n]+)+)',
        re.DOTALL
    )
    match = table_pattern.search(content)
    if match:
        updated = content[:match.end()] + '\n' + new_row + content[match.end():]
    else:
        updated = content.rstrip() + '\n' + new_row + '\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(updated)
    return True


def scan():
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    _parser.add_argument('--from-log', action='store_true', help='Read results from existing scan.log (no API calls)')
    _parser.add_argument('--date', default=None, help='Review date override')
    _args, _ = _parser.parse_known_args()
    use_json = _args.json
    from_log = _args.from_log

    if from_log:
        _run_from_log(use_json, _args.date or TODAY)
        return

    if not os.path.exists(WATCHLIST_DIR):
        print("watchlist 目錄不存在！")
        return

    files = [f for f in sorted(os.listdir(WATCHLIST_DIR))
             if f.endswith('.md') and f != 'template.md']
    if not files:
        print("watchlist 目錄內無追蹤標的。")
        return

    print(f"== Watchlist 掃描 {TODAY} ==\n")
    alert_stocks  = []
    n_plan_alerts = []
    policies = load_position_policies() if _ENGINES_AVAILABLE else {}
    signal_state = load_signal_state() if _ENGINES_AVAILABLE else {"signals": {}}

    for fname in files:
        code_match = re.match(r'(\d{4,6})', fname)
        if not code_match:
            continue
        code     = code_match.group(1)
        filepath = os.path.join(WATCHLIST_DIR, fname)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        name_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else fname

        print(f"[{code}] {name}")

        price, ma20, ma60, hist = get_market_data(code)
        if price is None:
            print(f"  無法取得市場資料，跳過。\n")
            continue
        data_date = hist.index[-1].date().isoformat() if hist is not None and not hist.empty else ""
        if data_date and data_date != TODAY:
            print(f"  市場資料日期 {data_date} != REVIEW_DATE {TODAY}，跳過避免污染。\n")
            continue

        ma20_pct = (price / ma20 - 1) * 100
        ma60_pct = (price / ma60 - 1) * 100
        print(f"  現價: {price:.2f}  |  月線(20MA): {ma20:.2f} ({ma20_pct:+.1f}%)  |  季線(60MA): {ma60:.2f} ({ma60_pct:+.1f}%)")

        fired = evaluate_triggers(price, ma20, ma60)
        if fired:
            print(f"  ⚡ 量化觸發：")
            for t in fired:
                print(f"     • {t}")
            alert_stocks.append((code, name, fired))
        else:
            print(f"  目前無量化觸發訊號")

        # ── N 計畫進場條件檢查 ────────────────────────────
        if code in ENTRY_PLANS:
            plan  = ENTRY_PLANS[code]
            snapshot = compute_wave_snapshot_silent(code, hist)
            wave = snapshot['total'] if snapshot else 0
            decision = None
            if snapshot:
                decision = evaluate_signal(
                    snapshot,
                    code=code,
                    strategy_class=policies.get(code, {}).get('strategy_class'),
                    policies=policies,
                    history=recent_entries(signal_state, code),
                )
                record_signal_state(
                    signal_state,
                    code=code,
                    as_of=TODAY,
                    source='watchlist_scan',
                    metrics=snapshot,
                    decision=decision,
                )
            policy_text = (
                f"{decision.strategy_label}｜{decision.recommendation}｜{decision.signal_quality_label}"
                if decision else "訊號政策未取得"
            )
            print(f"  📊 Wave摘要: {wave:+d}  |  政策: {policy_text}  （{plan['plan']} {plan['name']}）")

            triggered_conds = check_n_plan_conditions(code, price, hist, wave, plan, decision)
            if triggered_conds:
                for tc in triggered_conds:
                    print(f"  ⚠️ N計畫觸發 [{plan['plan']}-{tc['label']}]：{tc['description']}")
                    print(f"     → 建議動作：{tc['action']}（政策：{tc.get('policy', '')}）")
                    n_plan_alerts.append({
                        'code': code,
                        'name': plan['name'],
                        'plan': plan['plan'],
                        'condition_label': tc['label'],
                        'description': tc['description'],
                        'action': tc['action'],
                        'wave_score': wave,
                        'policy': tc.get('policy', ''),
                        'price': price,
                    })
            elif decision and not policy_allows_entry(decision):
                print(f"  ⛔ N計畫未觸發：價格/Wave 可能達標時仍需政策確認；目前 {policy_text}")
            else:
                for cond in plan.get('conditions', []):
                    if cond['type'] == 'zone':
                        if price > cond['price_max']:
                            gap_pct = (price / cond['price_max'] - 1) * 100
                            print(f"  ⏳ {plan['plan']}-{cond['label']}：現價比進場上限 {cond['price_max']} 高 {gap_pct:.1f}%，等回測")
                        elif price < cond['price_min']:
                            gap_pct = (cond['price_min'] / price - 1) * 100
                            print(f"  ⏳ {plan['plan']}-{cond['label']}：現價需漲 {gap_pct:.1f}% 才進入進場區間 {cond['price_min']}~{cond['price_max']}")
                    elif cond['type'] == 'above_consec':
                        if price < cond['price_threshold']:
                            gap_pct = (cond['price_threshold'] / price - 1) * 100
                            print(f"  ⏳ {plan['plan']}-{cond['label']}：現價需漲 {gap_pct:.1f}% 才達站穩門檻 {cond['price_threshold']}")

            stale_above = plan.get('plan_stale_above')
            if stale_above and price > stale_above:
                print(f"  ⚠️  {plan['plan']} 過期警示：現價 {price:.1f} > {stale_above}，{plan.get('plan_stale_note', '計畫應重新評估')}")

        # 更新 MD
        updated = append_today_record(filepath, price, ma20, ma60, fired)
        print(f"  MD 更新：{'已新增今日紀錄' if updated else '今日已有紀錄，跳過'}\n")

    # ── 儲存 N 計畫警示 ─────────────────────────────────
    if n_plan_alerts:
        save_entry_alerts(n_plan_alerts)
    if _ENGINES_AVAILABLE:
        save_signal_state(signal_state)

    # ── 總覽 ─────────────────────────────────────────────
    print("=" * 50)
    if n_plan_alerts:
        print(f"\n⚠️⚠️  N計畫進場觸發 — 共 {len(n_plan_alerts)} 個條件成立  ⚠️⚠️")
        for a in n_plan_alerts:
            print(f"  [{a['code']}] {a['name']} {a['plan']}-{a['condition_label']}")
            print(f"    條件：{a['description']}")
            print(f"    動作：{a['action']}")
            print(f"    Wave摘要: {a['wave_score']:+d}  |  現價: {a['price']:.1f}  |  政策: {a.get('policy', '')}")
        print(f"\n  已寫入 scripts/_entry_alerts.json，daily-review 將於步驟 9 顯示")
        print()

    if alert_stocks:
        print(f"!! 本次掃描共 {len(alert_stocks)} 檔觸發量化訊號，建議啟動研究：")
        for code, name, triggers in alert_stocks:
            print(f"  [{code}] {name}")
            for t in triggers:
                print(f"    -> {t}")
    else:
        print("本次掃描無量化觸發訊號，候補股持續觀察中。")
    print()
    print("注意：法人調升評等、外資加碼、供需報告等質化條件仍需人工確認。")

    if use_json:
        from hook_output import HookResult, HookTarget, output, today_str as _ts

        targets = []
        for a in n_plan_alerts:
            targets.append(HookTarget(
                code=a['code'], name=a['name'], action="p1_upgrade",
                summary=f"{a['plan']}-{a['condition_label']}: {a['description']}",
                detail={"plan": a['plan'], "price": a['price'], "wave_score": a['wave_score'], "policy": a.get('policy', ''), "action_text": a['action']},
            ))
        for code, name, triggers in alert_stocks:
            targets.append(HookTarget(
                code=code, name=name, action="todo_add",
                summary=f"量化觸發: {'; '.join(triggers)}",
                detail={"triggers": triggers},
            ))

        if targets:
            result = HookResult(
                hook="watchlist-entry-scan", timestamp=_ts(),
                status="alert", severity="medium", targets=targets,
            )
        else:
            result = HookResult(
                hook="watchlist-entry-scan", timestamp=_ts(),
                status="ok", severity="low",
            )
        output(result)


def _run_from_log(use_json: bool, review_date: str):
    """Read watchlist scan results from existing scan.log (no API calls)."""
    import re as _re
    LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'journals', 'logs')
    log_path = os.path.join(LOGS_DIR, f'{review_date}_scan.log')
    if not os.path.exists(log_path):
        if use_json:
            from hook_output import HookResult, output, today_str
            result = HookResult(
                hook="watchlist-entry-scan", timestamp=today_str(),
                status="warning", severity="low",
                error_message=f"scan.log not found: {log_path}",
            )
            output(result)
        else:
            print(f"scan.log not found: {log_path}")
        return

    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        log_text = f.read()

    # Parse N计划 triggered alerts from scan.log
    n_alerts = []
    for m in _re.finditer(r'N計畫觸發.*?\[(\w+-\w+)\].*?(\d{4}).*?(\S+)', log_text):
        n_alerts.append({"plan": m.group(1), "code": m.group(2), "name": m.group(3)})

    if use_json:
        from hook_output import HookResult, HookTarget, output, today_str

        targets = []
        for a in n_alerts:
            targets.append(HookTarget(
                code=a['code'], name=a['name'], action="p1_upgrade",
                summary=f"{a['plan']} 進場條件成立",
                detail=a,
            ))
        if targets:
            result = HookResult(
                hook="watchlist-entry-scan", timestamp=today_str(),
                status="alert", severity="medium", targets=targets,
            )
        else:
            result = HookResult(
                hook="watchlist-entry-scan", timestamp=today_str(),
                status="ok", severity="low",
            )
        output(result)
    else:
        if n_alerts:
            print(f"N計劃觸發 {len(n_alerts)} 個（from scan.log）")
            for a in n_alerts:
                print(f"  [{a['code']}] {a['name']} {a['plan']}")
        else:
            print("無 N計劃觸發（from scan.log）")


if __name__ == '__main__':
    scan()
