"""
wave_decay_alert.py — Wave Score 衰退警示器（hook 專用）

用法：
  python scripts/wave_decay_alert.py --code 6239 --name 力成 --alert-wave 0
  python scripts/wave_decay_alert.py --date 2026-05-04 --code 6239 --name 力成 --alert-wave 0
  python scripts/wave_decay_alert.py --code 6239 --name 力成 --alert-wave 0 --context "Wave ≤ 0 → 賣波段 80 股"

行為：
  - 計算指定標的當日 Wave Score（MA + GBM + 分位數 + 物理引擎，合計 -8~+8）
  - 若 Wave ≤ alert-wave，輸出 ⚠️ 警示（含觸發動作說明）
  - 若 Wave > alert-wave，輸出正常觀察行
  - 永遠 exit 0（hook 系統判斷 ⚠️ 關鍵字決定是否升級）
"""

import sys
import os
import argparse

sys.stdout.reconfigure(encoding='utf-8')

import warnings
import logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
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

STOCKS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stocks.csv')


def resolve_ticker(code: str) -> str:
    try:
        import csv
        with open(STOCKS_CSV, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['code'] == code:
                    return row['ticker']
    except Exception:
        pass
    return f'{code}.TW'


def fetch_ohlcv(ticker: str, period: str = '1y') -> pd.DataFrame | None:
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.columns = [c.title() for c in df.columns]
        return df.dropna() if not df.empty else None
    except Exception:
        return None


def calc_wave(df: pd.DataFrame) -> tuple[int, dict]:
    """回傳 (wave_total, components_dict)"""
    prices = df['Close']
    cur    = float(prices.iloc[-1])

    # 1. 均線結構
    ma5  = float(prices.tail(5).mean())
    ma10 = float(prices.tail(10).mean())
    ma20 = float(prices.tail(20).mean())
    ma60 = float(prices.tail(60).mean())
    ma_raw = sum([cur > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60])
    ma_score = ma_raw - 2

    # 2. GBM σ 位置
    log_ret = np.diff(np.log(prices.values))
    try:
        from arch import arch_model
        am = arch_model(log_ret * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
        res = am.fit(disp='off')
        sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
    except ImportError:
        sigma = np.std(log_ret, ddof=1) * np.sqrt(252)
    mu = (np.mean(log_ret) + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252

    T = 20 / 252
    E   = cur * np.exp(mu * T)
    std = sigma * np.sqrt(T) * cur
    if cur < E - 0.5 * std:
        gbm_score = 2
    elif cur <= E + 0.5 * std:
        gbm_score = 0
    elif cur <= E + std:
        gbm_score = -1
    else:
        gbm_score = -2

    # 3. 分位數
    q = compute_quantile_metrics(df)
    if cur >= q['sell_low']:
        q_score = -2
    elif cur >= q['buy_high']:
        q_score = 0
    elif cur >= q['buy_low']:
        q_score = 2
    elif cur >= q['deep_low']:
        q_score = 3
    else:
        q_score = -3

    # 4. 物理引擎（需完整 OHLCV）
    phys_df   = compute_physics(df)
    latest    = phys_df.iloc[-1]
    momentum  = latest.get('momentum', 0) or 0
    reynolds  = latest.get('reynolds', 0) or 0
    antigrav  = detect_antigravity(phys_df)
    ener_diss = detect_energy_dissipation(phys_df)
    phys_raw   = sum([momentum > 0, reynolds < 2000, not antigrav, not ener_diss])
    phys_score = phys_raw - 2

    total = ma_score + gbm_score + q_score + phys_score
    components = {
        'current': cur, 'ma20': ma20,
        'ma': ma_score, 'gbm': gbm_score, 'q': q_score, 'phys': phys_score,
        'mu': mu,
    }
    return total, components


def run():
    parser = argparse.ArgumentParser(description='Wave Score 衰退警示器')
    parser.add_argument('--code',        required=True,  help='股票代號')
    parser.add_argument('--name',        default='',     help='股票名稱（顯示用）')
    parser.add_argument('--alert-wave',  type=int, default=0,
                        help='Wave ≤ 此值時觸發警示（預設 0）')
    parser.add_argument('--context',     default='',
                        help='警示時補充的動作說明，例如「賣波段 80 股」')
    parser.add_argument('--period',      default='1y')
    parser.add_argument('--date', '--review-date', dest='review_date', default=None,
                        help='盤後歸屬日期（YYYY-MM-DD），補執行時使用')
    parser.add_argument('--json', action='store_true',
                        help='輸出結構化 JSON 供 hook_runner 使用')
    args = parser.parse_args()
    review_date = resolve_review_date(args.review_date)

    label = args.name or args.code
    ticker = resolve_ticker(args.code)

    df = fetch_ohlcv(ticker, args.period)
    if df is None or len(df) < 20:
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"wave-decay-{args.code}", timestamp=review_date,
                status="error", severity="medium",
                error_message=f"無法取得市場資料（ticker={ticker}）",
            )
            output(result)
            sys.exit(0)
        print(f"{label} Wave 觀察：⚠️ 無法取得市場資料（ticker={ticker}）")
        sys.exit(0)
    data_date = df.index[-1].date().isoformat()
    if data_date != review_date:
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"wave-decay-{args.code}", timestamp=review_date,
                status="warning", severity="low",
                error_message=f"資料日期 {data_date} != {review_date}，等待盤後更新",
            )
            output(result)
            sys.exit(0)
        print(
            f"{label} Wave 觀察：⚠️ 市場資料日期 {data_date} != REVIEW_DATE {review_date}，"
            "跳過避免污染訊號狀態"
        )
        sys.exit(0)

    try:
        wave, comp = calc_wave(df)
    except Exception as e:
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"wave-decay-{args.code}", timestamp=review_date,
                status="error", severity="high",
                error_message=f"計算失敗 — {e}",
            )
            output(result)
            sys.exit(0)
        print(f"{label} Wave 觀察：⚠️ 計算失敗 — {e}")
        sys.exit(0)

    cur   = comp['current']
    ma20  = comp['ma20']
    pct   = (cur / ma20 - 1) * 100
    breakdown = f"MA({comp['ma']:+d}) GBM({comp['gbm']:+d}) 分位({comp['q']:+d}) 物理({comp['phys']:+d})"
    volume = compute_volume_metrics(df)
    metrics = {
        'code': args.code,
        'current': cur,
        'ma20': ma20,
        'ma_s': comp['ma'],
        'gbm_s': comp['gbm'],
        'q_s': comp['q'],
        'phys_s': comp['phys'],
        'total': wave,
        **volume,
    }
    policies = load_position_policies()
    signal_state = load_signal_state()
    decision = evaluate_signal(
        metrics,
        code=args.code,
        strategy_class=policies.get(args.code, {}).get('strategy_class'),
        policies=policies,
        history=recent_entries(signal_state, args.code),
    )
    record_signal_state(
        signal_state,
        code=args.code,
        as_of=review_date,
        source='wave_decay_alert',
        metrics=metrics,
        decision=decision,
    )
    save_signal_state(signal_state)

    ratio = volume.get('volume_ratio')
    volume_line = (
        f"\n量能：今日 {ratio:.2f}x 5日均量 → {volume['volume_label']}"
        if isinstance(ratio, (int, float))
        else "\n量能：資料不足 → ⚪ 量能未知"
    )
    policy_line = (
        f"\n政策：{decision.strategy_label}｜{decision.recommendation}"
        f"｜品質 {decision.signal_quality_label}｜{decision.reason}"
    )

    threshold_hit = wave <= args.alert_wave
    policy_confirmed = decision.action_group == 'defensive' and decision.signal_quality != 'low'

    if args.json:
        from hook_output import HookResult, HookTarget, output

        hook_name = f"wave-decay-{args.code}"
        detail = {
            "wave_total": wave,
            "wave_components": {"ma": comp['ma'], "gbm": comp['gbm'], "q": comp['q'], "phys": comp['phys']},
            "current_price": round(cur, 1),
            "ma20": round(ma20, 1),
            "pct_from_ma": round(pct, 1),
            "threshold": args.alert_wave,
            "threshold_hit": threshold_hit,
            "policy_action_group": decision.action_group,
            "policy_quality": decision.signal_quality,
            "volume_ratio": ratio if isinstance(ratio, (int, float)) else None,
            "volume_label": volume.get('volume_label', ''),
        }
        if threshold_hit and policy_confirmed:
            targets = [HookTarget(
                code=args.code, name=label, action="p1_upgrade",
                summary=f"Wave {wave:+d} ≤ {args.alert_wave}，政策確認防守",
                detail=detail,
            )]
            result = HookResult(
                hook=hook_name, timestamp=review_date,
                status="alert", severity="high", targets=targets,
            )
        elif threshold_hit:
            targets = [HookTarget(
                code=args.code, name=label, action="p2_observe",
                summary=f"Wave {wave:+d} ≤ {args.alert_wave}，但政策未確認",
                detail=detail,
            )]
            result = HookResult(
                hook=hook_name, timestamp=review_date,
                status="warning", severity="medium", targets=targets,
            )
        else:
            result = HookResult(
                hook=hook_name, timestamp=review_date,
                status="ok", severity="low",
            )
        output(result)
        sys.exit(0)

    if threshold_hit and policy_confirmed:
        action = f" → {args.context}" if args.context else ""
        print(
            f"{label} Wave 觀察：🔴 Wave **{wave:+d}**（{breakdown}）"
            f"，現價 {cur:.1f}，MA20 {ma20:.1f}（{pct:+.1f}%）"
            f"{volume_line}{policy_line}"
            f"\n⚠️ Wave ≤ {args.alert_wave} 且政策確認防守訊號{action}"
        )
    elif threshold_hit:
        print(
            f"{label} Wave 觀察：🟡 Wave **{wave:+d}**（{breakdown}）"
            f"，現價 {cur:.1f}，MA20 {ma20:.1f}（{pct:+.1f}%）"
            f"{volume_line}{policy_line}"
            f"\n門檻（≤ {args.alert_wave}）命中，但政策未升級為防守警示；降級觀察"
        )
    else:
        print(
            f"{label} Wave 觀察：{'🟢' if wave >= 2 else '🟡'} Wave **{wave:+d}**（{breakdown}）"
            f"，現價 {cur:.1f}，MA20 {ma20:.1f}（{pct:+.1f}%）"
            f"{volume_line}{policy_line}"
            f"\n尚未達警示門檻（≤ {args.alert_wave}）"
        )

    sys.exit(0)


if __name__ == '__main__':
    run()
