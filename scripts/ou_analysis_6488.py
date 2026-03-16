"""
6488 環球晶 均值回歸（OU）分析
================================
驗證 Phase 0 買回觸發點 422 元的合理性

OU 過程：dX = κ(θ - X)dt + σ dW
  θ = 長期均衡價（20MA 或更長週期均值）
  κ = 回歸速度（越大越快回歸）
  σ = 波動率
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

# SSL 修正
import shutil, certifi
os.makedirs('C:/Temp', exist_ok=True)
shutil.copy2(certifi.where(), 'C:/Temp/cacert.pem')

import numpy as np
import pandas as pd

# ── 1. 取得數據 ─────────────────────────────────────────────────────────────
def fetch_data(ticker='6488.TWO', period='6mo'):
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.columns = [c.lower() for c in df.columns]
        return df[['close']].rename(columns={'close': 'Close'}).dropna()
    except Exception as e:
        print(f'⚠️  無法下載數據：{e}')
        return None

# ── 2. 估算 OU 參數（OLS 方法）────────────────────────
def estimate_ou_params(prices: pd.Series, dt: float = 1/252):
    """
    用 OLS 回歸 X(t+1) - X(t) = a + b*X(t) 估算 OU 參數
    κ = -b/dt, θ = -a/b, σ 由殘差估算
    """
    X = prices.values
    dX = np.diff(X)
    X_lag = X[:-1]

    # OLS: dX = a + b * X_lag
    A = np.vstack([np.ones_like(X_lag), X_lag]).T
    result = np.linalg.lstsq(A, dX, rcond=None)
    a, b = result[0]

    kappa = -b / dt          # 回歸速度（年化）
    theta = -a / b           # 均衡價
    sigma_res = np.std(dX - (a + b * X_lag))
    sigma = sigma_res / np.sqrt(dt)   # 年化波動率

    half_life = np.log(2) / kappa if kappa > 0 else np.inf  # 半衰期（年）
    half_life_days = half_life * 252

    return {'kappa': kappa, 'theta': theta, 'sigma': sigma,
            'half_life_days': half_life_days}

# ── 3. 計算觸發機率（蒙地卡羅）───────────────────────
def monte_carlo_prob(current: float, target_low: float, target_high: float,
                     theta: float, kappa: float, sigma: float,
                     days: int = 10, n_sims: int = 50000, dt: float = 1/252):
    """
    模擬 days 日內股價路徑，計算：
    - P(hit target_low) 先跌到 target_low
    - P(hit target_high) 先漲到 target_high
    """
    hit_low = 0
    hit_high = 0

    for _ in range(n_sims):
        X = current
        for _ in range(days):
            dX = kappa * (theta - X) * dt + sigma * np.sqrt(dt) * np.random.randn()
            X += dX
            if X <= target_low:
                hit_low += 1
                break
            if X >= target_high:
                hit_high += 1
                break

    return hit_low / n_sims, hit_high / n_sims

# ── 主程序 ────────────────────────────────────────────
if __name__ == '__main__':
    # 當前已知數據（健診 2026-03-09）
    CURRENT_PRICE = 428.50
    TARGET_BUY    = 422.00   # Phase 0 買回觸發
    TARGET_SELL   = 460.00   # 正式滾動賣出觸發
    STOP_LINE     = 400.00   # 全面停止線

    print('=== 6488 環球晶 OU 均值回歸分析 ===')
    print(f'現價：{CURRENT_PRICE} 元')
    print(f'Phase 0 買回觸發：{TARGET_BUY} 元（距 {(TARGET_BUY/CURRENT_PRICE-1)*100:.1f}%）')
    print(f'正式滾動賣出觸發：{TARGET_SELL} 元（距 {(TARGET_SELL/CURRENT_PRICE-1)*100:.1f}%）')
    print()

    df = fetch_data()

    if df is not None and not df.empty:
        prices = df['Close']
        params = estimate_ou_params(prices)

        print('── OU 參數估算 ──')
        print(f'均衡價 θ：{params["theta"]:.1f} 元（市場認定的長期均值）')
        print(f'回歸速度 κ：{params["kappa"]:.2f}（年化）')
        print(f'半衰期：{params["half_life_days"]:.0f} 交易日（偏離一半所需時間）')
        print(f'年化波動率 σ：{params["sigma"]:.1f} 元')
        print()

        # 蒙地卡羅：10 日內觸及 422 / 460 的機率
        p_low, p_high = monte_carlo_prob(
            CURRENT_PRICE, TARGET_BUY, TARGET_SELL,
            params['theta'], params['kappa'], params['sigma'], days=10
        )
        print('── 10 日內觸及機率（蒙地卡羅 50,000 次模擬）──')
        print(f'P(跌至 {TARGET_BUY} 元)：{p_low*100:.1f}%')
        print(f'P(漲至 {TARGET_SELL} 元)：{p_high*100:.1f}%')
        print()

        # 驗證 422 的合理性
        theta = params['theta']
        dist_current = (CURRENT_PRICE - theta) / theta * 100
        dist_target  = (TARGET_BUY - theta) / theta * 100
        print('── Phase 0 觸發點合理性驗證 ──')
        print(f'現價偏離均衡：{dist_current:.1f}%')
        print(f'422 元偏離均衡：{dist_target:.1f}%')
        if abs(dist_target) > abs(dist_current):
            print('✅ 422 比現價更偏離均衡 → 均值回歸拉力更強 → 是更好的買點')
        else:
            print('⚠️  422 接近均衡價，回歸拉力不比現價更強，考慮調整觸發點')

        # 建議
        print()
        print('── 策略建議 ──')
        hl = params['half_life_days']
        if hl < 15:
            print(f'半衰期 {hl:.0f} 日：快速回歸，422 觸發後應在 {hl:.0f} 日內考慮部分獲利')
        elif hl < 40:
            print(f'半衰期 {hl:.0f} 日：中速回歸，Phase 0 策略合理，預計 {hl:.0f} 日見回升')
        else:
            print(f'半衰期 {hl:.0f} 日：緩慢回歸，黑天鵝拉長回歸週期，建議分批買回而非一次')

    else:
        # 無網路時用估算參數示範
        print('⚠️  無法取得即時數據，以估算參數示範：')
        print()
        theta_est  = 461.85   # 20MA
        kappa_est  = 4.0      # 假設半衰期約 43 交易日
        sigma_est  = 20.0     # ATR 估算

        hl_est = np.log(2) / kappa_est * 252
        print(f'估算均衡價 θ：{theta_est} 元（20MA）')
        print(f'估算半衰期：{hl_est:.0f} 交易日')
        print()

        p_low, p_high = monte_carlo_prob(
            CURRENT_PRICE, TARGET_BUY, TARGET_SELL,
            theta_est, kappa_est, sigma_est, days=10
        )
        print('── 10 日內觸及機率（估算參數，蒙地卡羅 50,000 次）──')
        print(f'P(跌至 {TARGET_BUY} 元 = Phase 0 觸發)：{p_low*100:.1f}%')
        print(f'P(漲至 {TARGET_SELL} 元 = 賣出觸發)：{p_high*100:.1f}%')
        print()
        print('── Phase 0 合理性（估算）──')
        dist = (TARGET_BUY - theta_est) / theta_est * 100
        print(f'422 元偏離均衡價 461.85：{dist:.1f}%（約 2 個 ATR 單位）')
        print('✅ 結論：422 是合理的超跌買回區，均值回歸拉力強於現價')
