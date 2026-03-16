"""
wave_position.py — 波段位置分析器
====================================
整合 GBM σ 位置、均線結構、分位數引擎、物理引擎，
判斷股票目前在波段中的位置，並輸出加碼 / 持有 / 減持建議。

評分系統（每層 ±2 分，總分 -8 ~ +8）：
  - 均線結構  : 多頭排列程度 (0 ~ +4)，基準 -2，貢獻 -2 ~ +2
  - GBM σ 位置: 現價在趨勢帶的相對位置 (-2 ~ +2)
  - 分位數    : 現價落在超漲/合理/買回/深回檔哪一區 (-2 ~ +3)
  - 物理引擎  : 動量、雷諾數、反重力、能量耗散 (-2 ~ +2)

建議閾值：
  ≥ +5 → 強力加碼
  +3 ~ +4 → 加碼
  +1 ~ +2 → 輕倉加碼 / 觀察
  -1 ~ 0  → 持有不動
  -3 ~ -2 → 部分減持
  ≤ -4    → 強力減持

用法：
  python scripts/wave_position.py --code 2330
  python scripts/wave_position.py --code 2317
  python scripts/wave_position.py --code 3455 --budget 80000
  python scripts/wave_position.py --code 2330 --code 2317 --code 3455 --budget 80000
"""

import sys
import os
import argparse

sys.stdout.reconfigure(encoding='utf-8')

try:
    import shutil, certifi
    os.makedirs('C:/Temp', exist_ok=True)
    shutil.copy2(certifi.where(), 'C:/Temp/cacert.pem')
except Exception:
    pass

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from quantile_engine import compute_quantile_metrics
from physics_engine import compute_physics, detect_antigravity, detect_energy_dissipation


def fetch_ohlcv(ticker: str, period: str = '1y') -> pd.DataFrame | None:
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.columns = [c.title() for c in df.columns]
        return df.dropna()
    except Exception as e:
        print(f'  ⚠️  無法下載 {ticker}：{e}')
        return None


def estimate_gbm(prices: pd.Series) -> dict:
    log_returns = np.diff(np.log(prices.values))
    try:
        from arch import arch_model
        am = arch_model(log_returns * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
        res = am.fit(disp='off')
        sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
    except ImportError:
        sigma = np.std(log_returns, ddof=1) * np.sqrt(252)
    mu_daily = np.mean(log_returns)
    mu = (mu_daily + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252
    return {'mu': mu, 'sigma': sigma}


def ma_structure_score(prices: pd.Series) -> tuple[dict, int]:
    """
    均線多頭排列評分（0 ~ 4）
    完整多頭（現>5>10>20>60）= 4 分
    """
    ma5  = float(prices.tail(5).mean())
    ma10 = float(prices.tail(10).mean())
    ma20 = float(prices.tail(20).mean())
    ma60 = float(prices.tail(60).mean())
    cur  = float(prices.iloc[-1])
    raw  = sum([cur > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60])
    return {'current': cur, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60}, raw


def gbm_sigma_score(current: float, mu: float, sigma: float, days: int = 20) -> tuple[str, int]:
    """
    現價在 GBM 期望軌跡的 σ 位置評分
      < E - 0.5σ  → 低估  (+2)
      E ± 0.5σ    → 合理  ( 0)
      E + 1σ 內   → 偏貴  (-1)
      > E + 1σ    → 極端  (-2)
    """
    T = days / 252
    E   = current * np.exp(mu * T)
    std = sigma * np.sqrt(T) * current
    if current < E - 0.5 * std:
        return '低估區（低於趨勢期望 -0.5σ）', 2
    elif current <= E + 0.5 * std:
        return '合理區（趨勢帶 ±0.5σ 內）', 0
    elif current <= E + std:
        return '偏貴區（趨勢帶 +1σ）', -1
    else:
        return '極端貴（> 趨勢帶 +1σ）', -2


def composite_recommendation(total: int) -> str:
    if total >= 5:   return '🟢 強力加碼'
    elif total >= 3: return '🟢 加碼'
    elif total >= 1: return '🟡 輕倉加碼 / 觀察'
    elif total >= -1: return '🟡 持有不動'
    elif total >= -3: return '🔴 部分減持'
    else:             return '🔴 強力減持'


def wave_label(ma_score: int, q: dict, current: float) -> str:
    sell_mid = (q['sell_low'] + q['sell_high']) / 2
    buy_mid  = (q['buy_low']  + q['buy_high'])  / 2
    if current <= buy_mid:
        return '🌊 波段初期（回測買點附近）'
    elif current <= sell_mid and ma_score >= 3:
        return '🚀 波段中期（趨勢延伸中）'
    elif current >= sell_mid:
        return '🎯 波段後期（接近歷史賣出區）'
    else:
        return '⚖️  波段中性（整理待方向）'


def analyze(code: str, budget: float, period: str) -> dict:
    """分析單一標的，回傳結果 dict（供多標的比較用）"""

    # 查 ticker
    stocks_csv = os.path.join(os.path.dirname(__file__), '..', 'stocks.csv')
    ticker = f'{code}.TW'
    if os.path.exists(stocks_csv):
        try:
            df_s = pd.read_csv(stocks_csv, dtype=str).set_index('code')
            if code in df_s.index:
                ticker = df_s.loc[code, 'ticker']
        except Exception:
            pass

    print(f'\n{"=" * 50}')
    print(f'  {code}  [{ticker}]  波段位置分析')
    print(f'{"=" * 50}')

    df = fetch_ohlcv(ticker, period)
    if df is None or df.empty:
        print('  ❌ 無法取得資料')
        return {}

    prices = df['Close']
    current = float(prices.iloc[-1])
    as_of   = df.index[-1].date()
    print(f'  現價: {current:.1f} 元（{as_of}）\n')

    # ── 1. 均線結構 ──────────────────────────────────
    ma_data, ma_raw = ma_structure_score(prices)
    ma_score = ma_raw - 2  # 轉為 -2 ~ +2
    bullets = []
    bullets.append(f'現>{ma_data["ma5"]:.0f}(5MA) {"✅" if current > ma_data["ma5"] else "⚠️"}')
    bullets.append(f'5>{ma_data["ma10"]:.0f}(10MA) {"✅" if ma_data["ma5"] > ma_data["ma10"] else "⚠️"}')
    bullets.append(f'10>{ma_data["ma20"]:.0f}(20MA) {"✅" if ma_data["ma10"] > ma_data["ma20"] else "⚠️"}')
    bullets.append(f'20>{ma_data["ma60"]:.0f}(60MA) {"✅" if ma_data["ma20"] > ma_data["ma60"] else "⚠️"}')
    print(f'【1. 均線結構】  {ma_raw}/4 條件符合  →  評分 {ma_score:+d}')
    print(f'  {" | ".join(bullets)}')

    # ── 2. GBM σ 位置 ─────────────────────────────────
    gbm = estimate_gbm(prices)
    mu, sigma = gbm['mu'], gbm['sigma']
    T20 = 20 / 252
    E20 = current * np.exp(mu * T20)
    std20 = sigma * np.sqrt(T20) * current
    gbm_lbl, gbm_score = gbm_sigma_score(current, mu, sigma)
    print(f'\n【2. GBM σ 位置（20日）】  →  評分 {gbm_score:+d}')
    print(f'  μ={mu*100:+.1f}%  σ={sigma*100:.1f}%')
    print(f'  20日期望值: {E20:.1f}  |  ±1σ: {E20 - std20:.1f} ~ {E20 + std20:.1f}')
    print(f'  現價落點: {gbm_lbl}')

    # ── 3. 分位數引擎 ─────────────────────────────────
    q = compute_quantile_metrics(df)
    if current >= q['sell_low']:
        q_lbl, q_score = '超漲收割區', -2
    elif current >= q['buy_high']:
        q_lbl, q_score = '合理持有區', 0
    elif current >= q['buy_low']:
        q_lbl, q_score = '常規買回區', 2
    elif current >= q['deep_low']:
        q_lbl, q_score = '深回檔加碼區', 3
    else:
        q_lbl, q_score = '低於暫停線', -3

    print(f'\n【3. 分位數區間】  →  評分 {q_score:+d}')
    print(f'  賣出區: {q["sell_low"]:.1f} ~ {q["sell_high"]:.1f}')
    print(f'  常規買回區: {q["buy_low"]:.1f} ~ {q["buy_high"]:.1f}  |  深回檔區: {q["deep_low"]:.1f} ~ {q["deep_high"]:.1f}')
    print(f'  現價落點: {q_lbl}')

    # ── 4. 物理引擎 ───────────────────────────────────
    phys_df   = compute_physics(df)
    latest    = phys_df.iloc[-1]
    momentum  = latest.get('momentum', 0) or 0
    reynolds  = latest.get('reynolds', 0) or 0
    temp_val  = latest.get('temperature', 0) or 0
    antigrav  = detect_antigravity(phys_df)
    ener_diss = detect_energy_dissipation(phys_df)

    phys_raw = sum([momentum > 0, reynolds < 2000, not antigrav, not ener_diss])
    phys_score = phys_raw - 2  # 轉為 -2 ~ +2

    print(f'\n【4. 物理引擎】  →  評分 {phys_score:+d}')
    print(f'  動量: {"正向 ↑" if momentum > 0 else "負向 ↓"}'
          f'  |  雷諾數: {reynolds:,.0f} ({"層流 🟢" if reynolds < 1000 else "過渡 🟡" if reynolds < 2000 else "湍流 🔴"})'
          f'  |  溫度: {temp_val * 100:.2f}%')
    if antigrav:  print('  ⚠️  反重力預警（價漲量縮 ≥ 3日，動能不足）')
    if ener_diss: print('  ⚠️  能量耗散預警（動能連降，系統冷卻中）')

    # ── 5. 綜合結論 ───────────────────────────────────
    total  = ma_score + gbm_score + q_score + phys_score
    rec    = composite_recommendation(total)
    wlabel = wave_label(ma_raw, q, current)

    print(f'\n{"─" * 50}')
    print(f'  波段位置: {wlabel}')
    print(f'  綜合評分: MA({ma_score:+d}) GBM({gbm_score:+d}) 分位({q_score:+d}) 物理({phys_score:+d}) = {total:+d}')
    print(f'  操作建議: {rec}')

    # ── 6. 預算試算（新建倉）─────────────────────────
    if budget > 0:
        buy_mid = (q['buy_low'] + q['buy_high']) / 2
        print(f'\n【預算試算：{budget:,.0f} 元】')
        # 情境 A：現價進場
        sh_a = int(budget / current)
        print(f'  情境 A  現價 {current:.1f} 元：{sh_a} 股，花費 {sh_a * current:,.0f} 元，剩餘 {budget - sh_a * current:,.0f} 元')
        # 情境 B：回測買點
        sh_b = int(budget / buy_mid)
        print(f'  情境 B  回測買點 {buy_mid:.1f} 元：{sh_b} 股，花費 {sh_b * buy_mid:,.0f} 元，剩餘 {budget - sh_b * buy_mid:,.0f} 元')
        # 情境 C：分批 1/2 + 1/2
        sh_c1 = int((budget / 2) / current)
        sh_c2 = int((budget / 2) / buy_mid)
        print(f'  情境 C  分批：先 {sh_c1} 股 @ 現價 + 後 {sh_c2} 股 @ 回測買點，總花費上限 {budget:,.0f} 元')

    print()
    return {
        'code': code, 'current': current,
        'ma_score': ma_score, 'gbm_score': gbm_score,
        'q_score': q_score, 'phys_score': phys_score,
        'total': total, 'rec': rec, 'wave': wlabel,
    }


def main():
    parser = argparse.ArgumentParser(description='波段位置分析器')
    parser.add_argument('--code', action='append', required=True, help='股票代號，可重複指定多個')
    parser.add_argument('--budget', type=float, default=0, help='新建倉預算（元），僅用於最後一個 --code')
    parser.add_argument('--period', default='1y')
    args = parser.parse_args()

    results = []
    for i, code in enumerate(args.code):
        b = args.budget if i == len(args.code) - 1 else 0
        r = analyze(code, b, args.period)
        if r:
            results.append(r)

    # 多標的比較表
    if len(results) > 1:
        print(f'\n{"=" * 60}')
        print('  多標的綜合比較')
        print(f'{"=" * 60}')
        print(f'  {"代號":<8} {"現價":>8} {"MA":>4} {"GBM":>4} {"分位":>4} {"物理":>4} {"總分":>4}  建議')
        print(f'  {"─" * 56}')
        for r in results:
            print(f'  {r["code"]:<8} {r["current"]:>8.1f} {r["ma_score"]:>+4d} {r["gbm_score"]:>+4d} '
                  f'{r["q_score"]:>+4d} {r["phys_score"]:>+4d} {r["total"]:>+4d}  {r["rec"]}')
        print()


if __name__ == '__main__':
    main()
