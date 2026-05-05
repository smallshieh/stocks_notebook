"""
reentry_signal.py — 已減碼後的回補提醒

Example:
  python scripts/reentry_signal.py --code 1210 --name 大成 --armed-max-shares 1500 --min-wave 2 --reentry-shares 100
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, 'journals', 'logs')
TRADES_DIR = os.path.join(BASE_DIR, 'trades')


def find_trade_file(code: str) -> str:
    matches = glob.glob(os.path.join(TRADES_DIR, f'{code}_*.md'))
    return matches[0] if matches else ''


def parse_shares(trade_path: str) -> int | None:
    if not trade_path or not os.path.exists(trade_path):
        return None
    text = open(trade_path, 'r', encoding='utf-8').read()
    m = re.search(r'集保股數[^\d]*([\d,]+)', text)
    if not m:
        return None
    return int(m.group(1).replace(',', ''))


def load_wave_cache(today_str: str) -> dict:
    path = os.path.join(LOGS_DIR, f'{today_str}_wave_scores.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fmt_cmp(lhs: float, rhs: float) -> str:
    return '>' if lhs > rhs else '<='


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    parser.add_argument('--name', default='')
    parser.add_argument('--armed-max-shares', type=int, required=True)
    parser.add_argument('--min-wave', type=int, default=2)
    parser.add_argument('--reentry-shares', type=int, default=100)
    parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    args = parser.parse_args()

    today = os.environ.get('REVIEW_DATE') or datetime.date.today().strftime('%Y-%m-%d')
    label = args.name or args.code

    trade_path = find_trade_file(args.code)
    shares = parse_shares(trade_path)
    if shares is None:
        msg = f'{label} 回補觀察：找不到持股資料，暫不觸發'
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"reentry-{args.code}", timestamp=today,
                status="warning", severity="low", error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    if shares > args.armed_max_shares:
        msg = (
            f'{label} 回補觀察：未啟用，當前持股 {shares} 股，'
            f'尚未進入「先減碼後回補」狀態（需 ≤ {args.armed_max_shares} 股）'
        )
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"reentry-{args.code}", timestamp=today,
                status="ok", severity="low",
            )
            output(result)
            return
        print(msg)
        return

    wave_cache = load_wave_cache(today)
    row = wave_cache.get(args.code)
    if not row:
        msg = f'{label} 回補觀察：找不到 {today}_wave_scores.json 的 {args.code} 資料'
        if args.json:
            from hook_output import HookResult, HookTarget, output
            result = HookResult(
                hook=f"reentry-{args.code}", timestamp=today,
                status="warning", severity="low",
                error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    current = float(row['current'])
    ma20 = float(row['ma20'])
    wave = int(row['total'])
    above_ma = current > ma20
    wave_ok = wave >= args.min_wave

    if above_ma and wave_ok:
        msg = (
            f'{label} 回補條件達成：持股 {shares} 股，現價 {current:.2f} {fmt_cmp(current, ma20)} MA20 {ma20:.2f}，'
            f'Wave {wave:+d}，評估回補 {args.reentry_shares} 股試單'
        )
        if args.json:
            from hook_output import HookResult, HookTarget, output
            result = HookResult(
                hook=f"reentry-{args.code}", timestamp=today,
                status="alert", severity="medium",
                targets=[HookTarget(
                    code=args.code, name=label, action="todo_add",
                    summary=f"回補條件達成，評估回補 {args.reentry_shares} 股",
                    detail={"current_price": current, "ma20": ma20, "wave": wave, "shares": shares, "reentry_shares": args.reentry_shares},
                )],
            )
            output(result)
            return
        print(msg)
        return

    reasons = [
        f'現價 {current:.2f} {fmt_cmp(current, ma20)} MA20 {ma20:.2f}',
        f'Wave {wave:+d}{" 達標" if wave_ok else f" 未達 +{args.min_wave}"}',
    ]
    msg = f'{label} 回補觀察：持股 {shares} 股，' + '；'.join(reasons) + '，尚未達回補條件'
    if args.json:
        from hook_output import HookResult, output
        result = HookResult(
            hook=f"reentry-{args.code}", timestamp=today,
            status="ok", severity="low",
        )
        output(result)
        return
    print(msg)


if __name__ == '__main__':
    run()
