"""
deadline_counter.py — 硬死線倒計時工具

用途：計算距指定日期的剩餘交易日數，並在低於警戒值時輸出警示。
用法：
    python scripts/deadline_counter.py --code 8069 --name 元太 --deadline 2026-06-30 --alert-days 20
"""

import argparse
import os
import sys
from datetime import date, timedelta

def count_trading_days(start: date, end: date) -> int:
    """計算 start（不含）到 end（含）之間的交易日數（排除週末，不排除國定假日）。"""
    count = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:  # 0=Mon ... 4=Fri
            count += 1
        d += timedelta(days=1)
    return count

def main():
    parser = argparse.ArgumentParser(description="硬死線交易日倒計時")
    parser.add_argument("--code",       required=True,  help="股票代號，例如 8069")
    parser.add_argument("--name",       required=True,  help="股票名稱，例如 元太")
    parser.add_argument("--deadline",   required=True,  help="硬死線日期，格式 YYYY-MM-DD")
    parser.add_argument("--alert-days", type=int, default=20,
                        help="剩餘交易日數低於此值時輸出警示（預設 20）")
    parser.add_argument("--quiet",      action="store_true", help="無警示時僅輸出一行摘要")
    parser.add_argument("--json",       action="store_true", help="輸出結構化 JSON 供 hook_runner 使用")
    args = parser.parse_args()

    today      = date.fromisoformat(os.environ.get("REVIEW_DATE") or date.today().isoformat())
    deadline   = date.fromisoformat(args.deadline)
    remaining  = count_trading_days(today, deadline)
    alert_days = args.alert_days

    # 已過期
    if deadline < today:
        if args.json:
            from hook_output import HookResult, HookTarget, output
            result = HookResult(
                hook=f"deadline-{args.code}", timestamp=today.isoformat(), status="alert",
                severity="high",
                targets=[HookTarget(code=args.code, name=args.name, action="p1_upgrade",
                                    summary="硬死線已過期", detail={"deadline": args.deadline, "deadline_passed": True})],
                lifecycle_event="auto_disable",
            )
            output(result)
            sys.exit(0)
        print(f"⛔ {args.name} ({args.code}) 硬死線 {args.deadline} 已過期！請立即處理。")
        sys.exit(0)

    # 當日即硬死線
    if deadline == today:
        if args.json:
            from hook_output import HookResult, HookTarget, output
            result = HookResult(
                hook=f"deadline-{args.code}", timestamp=today.isoformat(), status="alert",
                severity="high",
                targets=[HookTarget(code=args.code, name=args.name, action="p1_upgrade",
                                    summary="硬死線就是今天", detail={"deadline": args.deadline, "remaining_trading_days": 0})],
                lifecycle_event="auto_disable",
            )
            output(result)
            return
        print(f"🚨 {args.name} ({args.code}) 硬死線就是今天（{args.deadline}）！必須今日完成清倉。")
        sys.exit(0)

    # 低於警戒值
    if remaining <= alert_days:
        if args.json:
            from hook_output import HookResult, HookTarget, output
            result = HookResult(
                hook=f"deadline-{args.code}", timestamp=today.isoformat(), status="alert",
                severity="high",
                targets=[HookTarget(
                    code=args.code, name=args.name, action="p1_upgrade",
                    summary=f"硬死線剩 {remaining} 交易日（≤ {alert_days} 警戒）",
                    detail={"deadline": args.deadline, "remaining_trading_days": remaining, "alert_days": alert_days},
                )],
            )
            output(result)
            return
        print(
            f"⚠️ {args.name} ({args.code}) 硬死線 {args.deadline}，"
            f"剩餘 {remaining} 個交易日（≤ {alert_days} 日警戒）— 已達門檻，建議評估執行時機。"
        )
    else:
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"deadline-{args.code}", timestamp=today.isoformat(), status="ok", severity="low",
            )
            output(result)
            return
        if not args.quiet:
            print(
                f"✅ {args.name} ({args.code}) 硬死線 {args.deadline}，"
                f"剩餘 {remaining} 個交易日，尚在安全範圍（警戒線 {alert_days} 日）。"
            )
        else:
            print(f"{args.name} 硬死線剩餘 {remaining} 個交易日")

if __name__ == "__main__":
    main()
