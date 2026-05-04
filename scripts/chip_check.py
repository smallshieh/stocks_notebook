#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chip_check.py — 三大法人籌碼核對

功能：
  1. 從 TWSE BFI82U API 抓取當日（或指定日期）三大法人買賣超金額
  2. 保存近 N 日歷史，計算連續外資買超天數
  3. 對照戰術指南的 A/B/C/D 四情境觸發條件
  4. 輸出結構化結果（Markdown 可直接貼入日誌），可供 daily-review 使用

用法：
  .venv/Scripts/python.exe scripts/chip_check.py
  .venv/Scripts/python.exe scripts/chip_check.py --date 20260421
  .venv/Scripts/python.exe scripts/chip_check.py --quiet   # 只輸出 Markdown 段落
"""

import sys
import json
import warnings
import datetime
import os

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

# ── SSL 修復（與其他腳本一致）────────────────────────────────────────────────
_FALLBACK_CERT = r"C:\Users\smallshieh\cacert.pem"
try:
    import certifi as _certifi
    _cert_path = _certifi.where()
    if not all(ord(c) < 128 for c in _cert_path) and os.path.exists(_FALLBACK_CERT):
        _cert_path = _FALLBACK_CERT
    os.environ["CURL_CA_BUNDLE"] = _cert_path
    os.environ.setdefault("SSL_CERT_FILE", _cert_path)
except ImportError:
    pass

from curl_cffi import requests as creq

# ─────────────────────────────────────────────────────────────────────────────
# 常數
# ─────────────────────────────────────────────────────────────────────────────

ROOT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(ROOT_DIR, "journals", "logs", "_chip_history.json")
TWSE_URL   = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"

# ─────────────────────────────────────────────────────────────────────────────
# 觸發情境定義
# （與戰術指南 📡 法人籌碼觸發條件表對應）
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = {
    "A": {
        "name": "多頭鞏固",
        "desc": "外資連三日買超 ≥ 30 億",
        "action": "波段倉持有，停利點不提前",
    },
    "B": {
        "name": "高檔出貨",
        "desc": "外資單日轉賣超 ≥ 30 億 + 爆量收黑",
        "action": "波段倉減碼（2330、2454、2382 優先）",
    },
    "C": {
        "name": "短線退潮",
        "desc": "投信翻買後連兩日撤退",
        "action": "觀察，不加碼",
    },
    "D": {
        "name": "對沖解除",
        "desc": "自營商避險部位單日翻買（由負轉正）",
        "action": "可輕倉跟進，N1 京元電觸發後評估",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# TWSE 資料抓取
# ─────────────────────────────────────────────────────────────────────────────

def fetch_chip(date_str: str) -> dict:
    """
    date_str: 'YYYYMMDD'
    回傳 dict: {
        'date': 'YYYY-MM-DD',
        'foreign':  float  (外資買賣超，億元，正=買超)
        'invest':   float  (投信)
        'dealer_self': float  (自營商自行買賣)
        'dealer_hedge': float (自營商避險)
        'dealer_total': float (自營商合計)
        'total':    float  (三大法人合計)
    }
    """
    resp = creq.get(
        TWSE_URL,
        params={"type": "day", "dayDate": date_str, "response": "json"},
        impersonate="chrome",
        verify=False,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE 回應異常：{data.get('stat')}")

    rows = {row[0]: row for row in data.get("data", [])}

    def parse_amt(key: str) -> float:
        row = rows.get(key)
        if not row:
            return 0.0
        val_str = row[3].replace(",", "").strip()  # 買賣差額欄（單位：元）
        return int(val_str) / 1e9  # 元 → 億元（1億=1e9元）

    foreign      = parse_amt("外資及陸資(不含外資自營商)")
    invest       = parse_amt("投信")
    dealer_self  = parse_amt("自營商(自行買賣)")
    dealer_hedge = parse_amt("自營商(避險)")
    dealer_total = dealer_self + dealer_hedge

    # 日期格式化
    d = date_str
    date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    return {
        "date":          date_fmt,
        "foreign":       round(foreign, 2),
        "invest":        round(invest, 2),
        "dealer_self":   round(dealer_self, 2),
        "dealer_hedge":  round(dealer_hedge, 2),
        "dealer_total":  round(dealer_total, 2),
        "total":         round(foreign + invest + dealer_total, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 歷史快取（存近 10 日）
# ─────────────────────────────────────────────────────────────────────────────

def load_history() -> list:
    if not os.path.exists(CACHE_FILE):
        return []
    with open(CACHE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_history(history: list):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    # 保留最近 10 筆，依日期排序
    seen, unique = set(), []
    for rec in sorted(history, key=lambda x: x["date"], reverse=True):
        if rec["date"] not in seen:
            seen.add(rec["date"])
            unique.append(rec)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(unique[:10], f, ensure_ascii=False, indent=2)


def upsert_today(history: list, today_rec: dict) -> list:
    """插入或更新今日紀錄"""
    updated = [r for r in history if r["date"] != today_rec["date"]]
    updated.append(today_rec)
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# 觸發情境判斷
# ─────────────────────────────────────────────────────────────────────────────

def check_scenarios(history: list, today: dict) -> dict:
    """
    history: 含今日的近期清單（已排序，最新在前）
    today:   今日資料
    回傳 {scenario_id: bool}
    """
    # 依日期排序（最新→最舊）
    sorted_hist = sorted(history, key=lambda x: x["date"], reverse=True)

    triggered = {}

    # ── 情境 A：外資連三日買超 ≥ 30 億 ────────────────────────────────────────
    consec_foreign_buy = 0
    for rec in sorted_hist:
        if rec["foreign"] >= 30:
            consec_foreign_buy += 1
        else:
            break
    triggered["A"] = consec_foreign_buy >= 3

    # ── 情境 B：外資單日轉賣超 ≥ 30 億（今日）──────────────────────────────────
    # 「轉賣超」= 今日 < -30，且前一日為買超
    prev = sorted_hist[1] if len(sorted_hist) >= 2 else None
    b_sell = today["foreign"] <= -30
    b_prev_buy = (prev["foreign"] > 0) if prev else False
    triggered["B"] = b_sell and b_prev_buy
    # 爆量收黑需人工確認（腳本標記 ⚠️）

    # ── 情境 C：投信翻買後連兩日撤退 ──────────────────────────────────────────
    # 前日投信 > 0，今日 < 0，且前前日投信也 < 0（連兩日撤退包含今日）
    if len(sorted_hist) >= 3:
        t0_inv  = sorted_hist[0]["invest"]   # 今日
        t1_inv  = sorted_hist[1]["invest"]   # 前日
        t2_inv  = sorted_hist[2]["invest"]   # 前前日
        # 翻買：前前日為買 → 前日買；今日轉賣 → 連兩日（前日轉今日）
        # 定義：在前 3 筆中，有一筆 > 0 後跟著連續 2 筆 < 0
        c_triggered = (t2_inv > 0) and (t1_inv < 0) and (t0_inv < 0)
        triggered["C"] = c_triggered
    else:
        triggered["C"] = False

    # ── 情境 D：自營商避險部位翻買（由負轉正）──────────────────────────────────
    if prev:
        triggered["D"] = (today["dealer_hedge"] > 0) and (prev["dealer_hedge"] < 0)
    else:
        triggered["D"] = False

    return triggered, consec_foreign_buy


# ─────────────────────────────────────────────────────────────────────────────
# 輸出格式
# ─────────────────────────────────────────────────────────────────────────────

def fmt_amt(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f} 億"


def build_report(today: dict, history: list, triggered: dict, consec_foreign: int) -> str:
    date = today["date"]

    # 近 5 日表格
    sorted_hist = sorted(history, key=lambda x: x["date"], reverse=True)[:5][::-1]  # 舊→新

    lines = [
        f"### 📡 三大法人籌碼（{date}）",
        "",
        "| 日期 | 外資 | 投信 | 自營自行 | 自營避險 | 合計 |",
        "|------|-----:|-----:|---------:|---------:|-----:|",
    ]
    for rec in sorted_hist:
        lines.append(
            f"| {rec['date']} "
            f"| {fmt_amt(rec['foreign'])} "
            f"| {fmt_amt(rec['invest'])} "
            f"| {fmt_amt(rec['dealer_self'])} "
            f"| {fmt_amt(rec['dealer_hedge'])} "
            f"| {fmt_amt(rec['total'])} |"
        )

    lines += [
        "",
        f"**外資連續買超天數**：{consec_foreign} 日（≥30億）",
        "",
        "#### 觸發情境核對",
        "",
        "| 情境 | 名稱 | 描述 | 命中 | 對應操作 |",
        "|------|------|------|:----:|---------|",
    ]

    for sid, meta in SCENARIOS.items():
        hit = triggered.get(sid, False)
        icon = "✅" if hit else "—"
        note = meta["action"] if hit else "（未命中）"
        # 情境 B 需補充說明
        desc = meta["desc"]
        if sid == "B" and hit:
            desc += "（爆量收黑需人工確認）"
        lines.append(f"| **{sid}** | {meta['name']} | {desc} | {icon} | {note} |")

    # 命中摘要
    hits = [sid for sid, v in triggered.items() if v]
    if hits:
        lines += [
            "",
            f"> ⚡ **命中情境 {', '.join(hits)}** — 請依對應操作更新待辦事項",
        ]
    else:
        lines += [
            "",
            "> ✔️ 今日無情境觸發，維持現有操作計畫",
        ]

    return "\n".join(lines)


def build_summary(today: dict, triggered: dict, consec_foreign: int) -> str:
    """精簡摘要，供 daily-review 整合用"""
    hits = [sid for sid, v in triggered.items() if v]
    hit_str = f"命中：{', '.join(hits)}" if hits else "無情境觸發"
    return (
        f"外資 {fmt_amt(today['foreign'])}（連買 {consec_foreign} 日）｜"
        f"投信 {fmt_amt(today['invest'])}｜"
        f"自營合計 {fmt_amt(today['dealer_total'])}｜"
        f"{hit_str}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def main():
    quiet   = "--quiet" in sys.argv
    summary = "--summary" in sys.argv  # 只輸出單行摘要（供 daily-review 呼叫）

    # 取得目標日期
    date_str = None
    for arg in sys.argv[1:]:
        if arg.startswith("--date="):
            date_str = arg.split("=", 1)[1].replace("-", "")
        elif arg == "--date" and len(sys.argv) > sys.argv.index(arg) + 1:
            date_str = sys.argv[sys.argv.index(arg) + 1].replace("-", "")

    if not date_str and os.environ.get("REVIEW_DATE"):
        date_str = os.environ["REVIEW_DATE"].replace("-", "")
    if not date_str:
        date_str = datetime.date.today().strftime("%Y%m%d")

    if not quiet and not summary:
        print(f"抓取 {date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 三大法人籌碼…")

    # 抓取資料
    try:
        today = fetch_chip(date_str)
    except Exception as e:
        print(f"❌ 無法取得籌碼資料：{e}")
        sys.exit(1)

    # 更新歷史快取
    history = load_history()
    history = upsert_today(history, today)
    save_history(history)

    # 觸發判斷
    triggered, consec_foreign = check_scenarios(history, today)

    if summary:
        print(build_summary(today, triggered, consec_foreign))
        return

    # 完整報告
    report = build_report(today, history, triggered, consec_foreign)

    if quiet:
        print(report)
    else:
        print(f"\n{'='*55}")
        print(f"日期    ：{today['date']}")
        print(f"外資    ：{fmt_amt(today['foreign'])}  （連買 ≥30億：{consec_foreign} 日）")
        print(f"投信    ：{fmt_amt(today['invest'])}")
        print(f"自營合計：{fmt_amt(today['dealer_total'])}（自行 {fmt_amt(today['dealer_self'])} / 避險 {fmt_amt(today['dealer_hedge'])}）")
        print(f"三大合計：{fmt_amt(today['total'])}")
        print(f"{'='*55}")

        hits = [sid for sid, v in triggered.items() if v]
        if hits:
            for sid in hits:
                m = SCENARIOS[sid]
                print(f"\n⚡ 情境 {sid}（{m['name']}）觸發！")
                print(f"   條件：{m['desc']}")
                print(f"   動作：{m['action']}")
        else:
            print("\n✔️  今日無情境觸發，維持現有操作計畫")

        print("\n── Markdown 段落（可貼入日誌）──")
        print(report)


if __name__ == "__main__":
    main()
