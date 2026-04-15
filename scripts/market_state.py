#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_state.py — 台股大盤狀態儀表板

功能：
  - 抓取加權指數（^TWII）近 1 年資料
  - 計算多條均線位置與排列
  - 成交量結構（今日 vs 20日均量）
  - 判斷市場狀態（多頭確立 / 多頭震盪 / 盤整 / 空頭初期 / 空頭確立 / 危機）
  - 輸出建議的 Core:Tactical:Cash 動態比例
  - 輸出可貼入日誌的 Markdown 段落

用法：
  .venv/Scripts/python.exe scripts/market_state.py
  .venv/Scripts/python.exe scripts/market_state.py --quiet   # 只輸出 Markdown 段落
"""

import sys
import warnings
import os
import datetime

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import logging
logging.disable(logging.CRITICAL)

# ── SSL 修復 ──────────────────────────────────────────────────────────────────
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
import yfinance as yf
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# 市場狀態定義
# ─────────────────────────────────────────────────────────────────────────────

REGIMES = {
    'bull_strong': {
        'label': '🚀 多頭確立',
        'desc': '均線多頭排列，量能健康，趨勢向上',
        'core': 40, 'tactical': 40, 'cash': 20,
        'action': '攻擊模式：子彈優先 Tactical，Core 不追加',
    },
    'bull_weak': {
        'label': '📈 多頭震盪',
        'desc': '均線偏多但不整齊，量能縮減或不穩',
        'core': 45, 'tactical': 35, 'cash': 20,
        'action': '偏攻擊：Tactical 謹慎建倉，Core 不動',
    },
    'sideways': {
        'label': '➡️ 盤整',
        'desc': '均線糾結，方向不明，多空拉鋸',
        'core': 50, 'tactical': 30, 'cash': 20,
        'action': '平衡模式：等待方向確認，縮減新倉規模',
    },
    'bear_early': {
        'label': '⚠️ 空頭初期',
        'desc': '現價跌破月線，均線開始空頭排列',
        'core': 55, 'tactical': 20, 'cash': 25,
        'action': '防禦模式：停止新 Tactical 建倉，現金優先',
    },
    'bear_confirmed': {
        'label': '🔴 空頭確立',
        'desc': '月線跌破季線，均線全面空頭排列',
        'core': 55, 'tactical': 15, 'cash': 30,
        'action': '強防禦：持續減少 Tactical，累積現金等候底部',
    },
    'crisis': {
        'label': '🚨 危機 / 黑天鵝',
        'desc': '系統性恐慌，急速跌破年線或季線',
        'core': 50, 'tactical': 10, 'cash': 40,
        'action': '極度防禦：保留現金，等恐慌尾端逆向布局',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 資料抓取
# ─────────────────────────────────────────────────────────────────────────────

def fetch_twii():
    session = creq.Session(verify=False, impersonate='chrome')
    ticker = yf.Ticker('^TWII', session=session)
    hist = ticker.history(period='1y', auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError('無法取得加權指數資料')
    return hist


# ─────────────────────────────────────────────────────────────────────────────
# 指標計算
# ─────────────────────────────────────────────────────────────────────────────

def compute_indicators(hist: pd.DataFrame) -> dict:
    close = hist['Close']
    volume = hist['Volume']

    price = close.iloc[-1]
    ma5   = close.rolling(5).mean().iloc[-1]
    ma10  = close.rolling(10).mean().iloc[-1]
    ma20  = close.rolling(20).mean().iloc[-1]
    ma60  = close.rolling(60).mean().iloc[-1]
    ma120 = close.rolling(min(120, len(close))).mean().iloc[-1]
    ma252 = close.rolling(min(252, len(close))).mean().iloc[-1]

    vol_today = volume.iloc[-1]
    vol_ma20  = volume.rolling(20).mean().iloc[-1]
    vol_ratio = vol_today / vol_ma20 if vol_ma20 > 0 else 1.0

    # 近 5 日漲跌
    chg_1d = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    chg_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0

    return {
        'price': price,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
        'ma60': ma60, 'ma120': ma120, 'ma252': ma252,
        'vol_today': vol_today, 'vol_ma20': vol_ma20, 'vol_ratio': vol_ratio,
        'chg_1d': chg_1d, 'chg_5d': chg_5d,
        'date': hist.index[-1].strftime('%Y-%m-%d'),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 均線排列分數（0-5）
# ─────────────────────────────────────────────────────────────────────────────

def ma_bull_score(d: dict) -> int:
    """計算多頭排列條件數（越高越多頭）"""
    score = 0
    if d['price'] > d['ma20']:  score += 1
    if d['price'] > d['ma60']:  score += 1
    if d['ma20']  > d['ma60']:  score += 1
    if d['ma60']  > d['ma120']: score += 1
    if d['ma20']  > d['ma120']: score += 1
    return score  # 0-5


# ─────────────────────────────────────────────────────────────────────────────
# 市場狀態判斷
# ─────────────────────────────────────────────────────────────────────────────

def classify_regime(d: dict) -> str:
    score = ma_bull_score(d)
    vol   = d['vol_ratio']
    chg5  = d['chg_5d']

    # 危機：跌破年線且近 5 日跌幅 > 8%
    if d['price'] < d['ma252'] and chg5 < -8:
        return 'crisis'

    # 空頭確立：月線跌破季線
    if d['ma20'] < d['ma60'] and score <= 1:
        return 'bear_confirmed'

    # 空頭初期：跌破月線，均線開始空排
    if d['price'] < d['ma20'] and score <= 2:
        return 'bear_early'

    # 多頭確立：均線 4/5 以上多頭排列，量能健康（vol_ratio > 0.8）
    # 若量比資料異常（< 0.01，盤中未結算或資料缺失），忽略量能條件，純用均線判斷
    vol_valid = vol >= 0.01
    if score >= 4 and (not vol_valid or vol >= 0.8):
        # 降級條件：現價跌破月線 → 上升趨勢中的短期修正，降為多頭震盪
        if d['price'] < d['ma20']:
            return 'bull_weak'
        return 'bull_strong'

    # 多頭震盪：均線 3-4 多頭但量縮或不穩
    if score >= 3:
        return 'bull_weak'

    # 盤整：其餘情況
    return 'sideways'


# ─────────────────────────────────────────────────────────────────────────────
# 輸出
# ─────────────────────────────────────────────────────────────────────────────

def format_ma_row(label, price, ma_val):
    diff = (price - ma_val) / ma_val * 100
    flag = '✅' if price > ma_val else '🔴'
    return f"| {label} | {ma_val:,.0f} | {diff:+.1f}% | {flag} |"


def build_report(d: dict, regime_key: str) -> str:
    r = REGIMES[regime_key]
    today = datetime.date.today().strftime('%Y-%m-%d')

    lines = [
        f"## 📊 大盤狀態儀表板（{today}）",
        "",
        f"### 市場狀態：{r['label']}",
        f"> {r['desc']}",
        "",
        f"**加權指數**：{d['price']:,.0f} 點　今日 {d['chg_1d']:+.1f}%　近5日 {d['chg_5d']:+.1f}%",
        f"**成交量**：{d['vol_today']/1e8:.1f} 億　（均量 {d['vol_ma20']/1e8:.1f} 億，比率 {d['vol_ratio']:.2f}x）",
        "",
        "| 均線 | 點位 | 價差% | 狀態 |",
        "|------|------|-------|------|",
        format_ma_row('MA5',   d['price'], d['ma5']),
        format_ma_row('MA10',  d['price'], d['ma10']),
        format_ma_row('MA20（月線）', d['price'], d['ma20']),
        format_ma_row('MA60（季線）', d['price'], d['ma60']),
        format_ma_row('MA120（半年線）', d['price'], d['ma120']),
        format_ma_row('MA252（年線）', d['price'], d['ma252']),
        "",
        f"**均線多頭排列分數**：{ma_bull_score(d)} / 5",
        "",
        "### 建議資產配置",
        f"| 桶別 | 建議比例 | 預設目標 | 方向 |",
        f"|------|---------|---------|------|",
        f"| Core  | **{r['core']}%** | 50% | {'⬇️ 壓縮' if r['core'] < 50 else '⬆️ 擴張' if r['core'] > 50 else '－ 維持'} |",
        f"| Tactical | **{r['tactical']}%** | 30% | {'⬆️ 擴張' if r['tactical'] > 30 else '⬇️ 壓縮' if r['tactical'] < 30 else '－ 維持'} |",
        f"| Cash | **{r['cash']}%** | 20% | {'⬆️ 擴張' if r['cash'] > 20 else '⬇️ 壓縮' if r['cash'] < 20 else '－ 維持'} |",
        "",
        f"**操作指引**：{r['action']}",
    ]
    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def main():
    quiet = '--quiet' in sys.argv

    if not quiet:
        print("抓取加權指數資料…")

    try:
        hist = fetch_twii()
    except Exception as e:
        print(f"❌ 無法取得資料：{e}")
        sys.exit(1)

    d = compute_indicators(hist)
    regime = classify_regime(d)
    report = build_report(d, regime)

    if quiet:
        print(report)
    else:
        r = REGIMES[regime]
        print(f"\n{'='*50}")
        print(f"加權指數：{d['price']:,.0f}　（{d['date']}）")
        print(f"市場狀態：{r['label']}")
        print(f"均線分數：{ma_bull_score(d)}/5　量比：{d['vol_ratio']:.2f}x")
        print(f"建議配置：Core {r['core']}% / Tactical {r['tactical']}% / Cash {r['cash']}%")
        print(f"操作指引：{r['action']}")
        print(f"{'='*50}\n")
        print("── Markdown 段落（可貼入日誌）──")
        print(report)


if __name__ == '__main__':
    main()
