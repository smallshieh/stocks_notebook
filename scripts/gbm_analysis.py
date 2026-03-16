"""
gbm_analysis.py — 幾何布朗運動（GBM）機率預測工具
===================================================
適用：具備長期向上趨勢特性的標的（如台積電 2330、0050 等大盤指數）。
不適用：景氣循環股、區間震盪股（請使用 ou_analysis.py）。

模型：幾何布朗運動 (Geometric Brownian Motion)
  dS = μ*S*dt + σ*S*dW
  - μ (漂移率, Drift)：代表長期趨勢的斜率。
  - σ (波動率, Volatility)：價格震盪程度。

特點：
  - 價格呈對數常態分佈，長期期望值隨時間指數增長。
  - 使用 GARCH(1,1) 估計當夏的動態波動率（若未安裝 arch，退回歷史標準差）。
  - 臺股上市：2330.TW (.TW 後綴)
  - 臺股上櫃：6488.TWO (.TWO 後綴)
  - 美股標的：DTIL, TSLA (不加後綴，但需在 stocks.csv 的 ticker 欄位填寫正確)

用法範例:
  - python scripts/gbm_analysis.py --code 2330
  - python scripts/gbm_analysis.py --code 0050 --days 10,20,60
  - python scripts/gbm_analysis.py --code DTIL --days 20,60,252
"""

import sys
import os
import argparse
import math

sys.stdout.reconfigure(encoding='utf-8')

try:
    import shutil, certifi
    os.makedirs('C:/Temp', exist_ok=True)
    shutil.copy2(certifi.where(), 'C:/Temp/cacert.pem')
except Exception:
    pass

import numpy as np
import pandas as pd

def fetch_data(ticker: str, period: str = '1y') -> pd.DataFrame | None:
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.columns = [c.lower() for c in df.columns]
        return df[['close']].rename(columns={'close': 'Close'}).dropna()
    except Exception as e:
        print(f'⚠️  無法下載 {ticker} 數據：{e}')
        return None

def estimate_gbm_params(prices: pd.Series) -> dict:
    """
    從歷史價格序列估算 GBM 的漂移率 (mu) 和波動率 (sigma)。
    """
    # 日期對數報酬率
    log_returns = np.diff(np.log(prices.values))
    dt = 1/252

    # --- 波動率 σ：優先使用 GARCH(1,1) 動態估計 ---
    try:
        from arch import arch_model
        # 放大 100 倍以助 GARCH 收斂
        am = arch_model(log_returns * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
        res = am.fit(disp='off')
        # 取最新一天的條件波動率 (還原)
        last_cond_vol = res.conditional_volatility[-1] / 100
        sigma = last_cond_vol * np.sqrt(252)
        vol_type = 'GARCH(1,1) 動態'
    except ImportError:
        sigma_daily = np.std(log_returns, ddof=1)
        sigma = sigma_daily * np.sqrt(252)
        vol_type = '靜態標準差'

    # 漂移率 μ
    mu_daily = np.mean(log_returns)
    # 根據 ITO 引理，年度 Drift = (日均值 + 0.5 * 日波動率^2) * 252
    mu = (mu_daily + 0.5 * (sigma / np.sqrt(252))**2) * 252

    return {
        'mu': mu,
        'sigma': sigma,
        'vol_type': vol_type
    }

def monte_carlo_gbm(current: float, target_low: float, target_high: float,
                    mu: float, sigma: float, days: int = 20, 
                    n_sims: int = 30000) -> tuple[float, float, float]:
    """
    模擬 days 日內 GBM 路徑，計算：
    - P(先向上突破 target_high)
    - P(先向下跌破 target_low)
    - n_days 後的期望值 (Expected Value)
    """
    hit_low = 0
    hit_high = 0
    dt = 1/252

    for _ in range(n_sims):
        # 使用 GBM 封閉解的離散化：
        # S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
        # S(T) = S(0) * exp( (mu - 0.5*sigma^2)*T + sigma*sqrt(dt)*sum(Z) )
        
        # S(T):
        dw = np.random.randn(days)
        # 計算累積路徑以檢查是否提早觸及目標
        drift_array = (mu - 0.5 * sigma**2) * dt
        shock_array = sigma * np.sqrt(dt) * dw
        daily_returns = drift_array + shock_array
        
        # 從 0 開始的累積對數報酬率
        cum_returns = np.cumsum(daily_returns)
        # 還原為價格路徑
        path = current * np.exp(cum_returns)

        # 檢查是否觸碰目標
        if np.any(path >= target_high):
            hit_high += 1
        elif np.any(path <= target_low):
            hit_low += 1

    # GBM T 時間後的期望值為 S0 * exp(mu * T)
    expected_val = current * np.exp(mu * (days / 252))
    
    return hit_low / n_sims, hit_high / n_sims, expected_val

def auto_targets(current: float, sigma: float, days: int = 20):
    """
    對趨勢股，以波動率動態計算上方和下方的合理目標。
    通常以上下 1 和 1.5 個標準差作為目標。
    """
    T = days / 252
    std_dev = sigma * np.sqrt(T)
    # 使用指數計算目標 (因為價格是對數常態)
    t_up = [current * np.exp(std_dev), current * np.exp(1.5 * std_dev)]
    t_dn = [current * np.exp(-std_dev), current * np.exp(-1.5 * std_dev)]
    return sorted(t_up), sorted(t_dn, reverse=True)


def main():
    parser = argparse.ArgumentParser(description='幾何布朗運動（GBM）機率預測工具（適合趨勢股）')
    parser.add_argument('--code', required=True, help='股票代號，如 2330 或 0050')
    parser.add_argument('--market', default='auto', choices=['auto', 'TW', 'TWO'])
    parser.add_argument('--period', default='1y', help='資料期間，預設 1y 較能捕捉長趨勢')
    parser.add_argument('--days', default='10,20,60', help='預測天數，預設 10,20,60')
    parser.add_argument('--sims', default=30000, type=int)
    args = parser.parse_args()

    # 查 CSV 或猜測
    code = args.code
    ticker_from_csv = None
    stocks_csv = os.path.join(os.path.dirname(__file__), '..', 'stocks.csv')
    if os.path.exists(stocks_csv):
        try:
            stocks_df = pd.read_csv(stocks_csv, dtype=str).set_index('code')
            if code in stocks_df.index and 'ticker' in stocks_df.columns:
                ticker_from_csv = stocks_df.loc[code, 'ticker']
        except Exception:
            pass

    if ticker_from_csv:
        tickers = [ticker_from_csv]
    elif args.market == 'auto':
        tickers = [f'{code}.TW', f'{code}.TWO'] # 趨勢型標的通常是上市，先猜 TW
    elif args.market == 'TW':
        tickers = [f'{code}.TW']
    else:
        tickers = [f'{code}.TWO']

    df = None
    for ticker in tickers:
        df = fetch_data(ticker, args.period)
        if df is not None and not df.empty:
            print(f'✅ 資料來源：{ticker}（{len(df)} 筆，近 {args.period}）')
            break

    if df is None or df.empty:
        print('❌ 無法取得資料')
        return

    prices = df['Close']
    current = prices.iloc[-1]
    params = estimate_gbm_params(prices)

    mu = params['mu']
    sigma = params['sigma']
    vol_type = params['vol_type']

    print()
    print(f'=== {code} GBM 幾何布朗運動機率預測 ===')
    print(f'現價            ：{current:.1f} 元')
    print(f'趨勢漂移率 μ      ：{mu*100:+.1f}% (年化，正值代表長期看漲)')
    print(f'年化波動率 σ      ：{sigma*100:.1f}%（以 {vol_type} 估計）')
    
    if mu <= 0:
        print(f'⚠️ 警告：過去 {args.period} μ ≤ 0，該標的目前不具備長期向上趨勢特徵，可能不適合 GBM 模型。')

    day_list = [int(d) for d in args.days.split(',')]

    for days in day_list:
        print(f'\n【未來 {days} 交易日】')
        t_up, t_dn = auto_targets(current, sigma, days)
        
        expected_val = current * np.exp(mu * (days / 252))
        print(f'  🎯 {days}日後期望價：{expected_val:.1f} 元')

        print('  [向上突破機率]')
        for th in t_up:
            _, p_h, _ = monte_carlo_gbm(current, 0, th, mu, sigma, days=days, n_sims=args.sims)
            bar = '█' * int(p_h * 20)
            print(f'    漲至 {th:>6.1f} 元：{p_h*100:5.1f}%  {bar}')
            
        print('  [向下跌破機率]')
        for tl in t_dn:
            p_l, _, _ = monte_carlo_gbm(current, tl, 999999, mu, sigma, days=days, n_sims=args.sims)
            bar = '█' * int(p_l * 20)
            print(f'    跌至 {tl:>6.1f} 元：{p_l*100:5.1f}%  {bar}')

    print('\n💡 GBM 特性提醒：機率不對稱，只要 μ > 0，長期向下突破機率會因為趨勢帶動而顯著低於向上突破。')

if __name__ == '__main__':
    main()
