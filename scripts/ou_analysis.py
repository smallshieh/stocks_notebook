"""
ou_analysis.py — 通用均值回歸（OU）機率預測工具
================================================
Ornstein-Uhlenbeck 隨機微分方程 + 蒙地卡羅模擬

OU 過程：dX = κ(θ - X)dt + σ dW
  θ = 長期均衡價（由歷史收盤 OLS 估算）
  κ = 回歸速度（年化）
  σ = 波動率（年化）

用法：
  # 基本使用（自動推算目標價）
  python scripts/ou_analysis.py --code 6488

  # 上市股（.TW）
  python scripts/ou_analysis.py --code 2330 --market TW

  # 自訂目標價
  python scripts/ou_analysis.py --code 5483 --targets-up 118,125,130 --targets-down 110,107,100

  # 自訂模擬天數與次數
  python scripts/ou_analysis.py --code 6488 --days 5,10,20 --sims 30000
"""

import sys
import os
import argparse
import math

sys.stdout.reconfigure(encoding='utf-8')

# SSL 修正（curl_cffi / yfinance 需要）
try:
    import shutil, certifi
    os.makedirs('C:/Temp', exist_ok=True)
    shutil.copy2(certifi.where(), 'C:/Temp/cacert.pem')
except Exception:
    pass

import numpy as np
import pandas as pd


# ── 1. 取得數據 ─────────────────────────────────────────────────────────────

def fetch_data(ticker: str, period: str = '6mo') -> pd.DataFrame | None:
    """
    從 yfinance 取得歷史收盤資料。
    ticker 格式：上市 XXXX.TW，上櫃 XXXX.TWO
    """
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


# ── 2. 估算 OU 參數（OLS 方法）────────────────────────────────────────────

def estimate_ou_params(prices: pd.Series, dt: float = 1/252) -> dict:
    """
    用 OLS 回歸 ΔX = a + b*X(t) 估算 OU 參數。
    回傳：{'kappa', 'theta', 'sigma', 'half_life_days'}
    """
    X = prices.values
    dX = np.diff(X)
    X_lag = X[:-1]

    A = np.vstack([np.ones_like(X_lag), X_lag]).T
    result = np.linalg.lstsq(A, dX, rcond=None)
    a, b = result[0]

    kappa = -b / dt
    theta = -a / b

    # --- 波動率 σ：改用 GARCH(1,1) 動態估計 ---
    # 計算對數報酬率，放大 100 倍以利 GARCH 收斂
    returns = np.diff(np.log(X)) * 100
    try:
        from arch import arch_model
        # 建立 GARCH(1,1) 模型
        am = arch_model(returns, vol='Garch', p=1, o=0, q=1, dist='Normal')
        res = am.fit(disp='off')
        # 取最新一天的條件波動率 (已經放大 100 倍，還原回來)
        last_cond_vol = res.conditional_volatility[-1] / 100
        # GARCH 是日波動率，轉為年化波動率 σ
        sigma = last_cond_vol * np.sqrt(252)
        vol_type = 'GARCH(1,1) 動態'
    except ImportError:
        # 若無 arch 套件，退回原本的 OLS 殘差標準差
        sigma_res = np.std(dX - (a + b * X_lag))
        sigma = sigma_res / np.sqrt(dt)
        vol_type = 'OLS 靜態'

    half_life = np.log(2) / kappa if kappa > 0 else np.inf
    half_life_days = half_life * 252

    return {
        'kappa': kappa,
        'theta': theta,
        'sigma': sigma,
        'half_life_days': half_life_days,
        'vol_type': vol_type
    }


# ── 3. 蒙地卡羅觸及機率 ────────────────────────────────────────────────────

def monte_carlo_prob(current: float, target_low: float, target_high: float,
                     theta: float, kappa: float, sigma: float,
                     days: int = 10, n_sims: int = 30000,
                     dt: float = 1/252) -> tuple[float, float]:
    """
    模擬 OU 路徑，計算 days 日內：
    - P(先觸及 target_low)
    - P(先觸及 target_high)
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


# ── 4. 自動推算合理目標價 ──────────────────────────────────────────────────

def auto_targets(current: float, step: float = 5.0, n: int = 4):
    """
    以 step 為間距，往上往下各 n 個目標價。
    """
    base_up = math.ceil(current / step) * step
    base_dn = math.floor(current / step) * step
    targets_up = [base_up + step * i for i in range(1, n + 1)]
    targets_dn = [base_dn - step * i for i in range(1, n + 1)]
    return targets_up, targets_dn


# ── 主程序 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='OU 均值回歸機率預測（通用版）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--code', required=True,
                        help='股票代號，如 6488 或 2330')
    parser.add_argument('--market', default='auto',
                        choices=['auto', 'TW', 'TWO'],
                        help='市場：TW=上市，TWO=上櫃，auto=自動嘗試（預設）')
    parser.add_argument('--period', default='6mo',
                        help='歷史資料期間，如 3mo, 6mo, 1y（預設 6mo）')
    parser.add_argument('--days', default='5,10,20',
                        help='預測天數（逗號分隔，預設 5,10,20）')
    parser.add_argument('--sims', default=30000, type=int,
                        help='蒙地卡羅模擬次數（預設 30000）')
    parser.add_argument('--targets-up', default=None,
                        help='自訂上漲目標（逗號分隔），若未填則自動推算')
    parser.add_argument('--targets-down', default=None,
                        help='自訂下跌目標（逗號分隔），若未填則自動推算')
    parser.add_argument('--step', default=5.0, type=float,
                        help='自動推算目標時的間距（預設 5 元）')
    args = parser.parse_args()

    # 決定 ticker：優先查 stocks.csv，再暴力嘗試
    code = args.code
    ticker_from_csv = None
    stocks_csv = os.path.join(os.path.dirname(__file__), '..', 'stocks.csv')
    if os.path.exists(stocks_csv):
        try:
            import pandas as pd
            stocks_df = pd.read_csv(stocks_csv, dtype=str).set_index('code')
            if code in stocks_df.index and 'ticker' in stocks_df.columns:
                ticker_from_csv = stocks_df.loc[code, 'ticker']
        except Exception:
            pass

    if ticker_from_csv:
        tickers = [ticker_from_csv]
        print(f'📋 stocks.csv 查詢：{code} → {ticker_from_csv}')
    elif args.market == 'auto':
        tickers = [f'{code}.TWO', f'{code}.TW']  # fallback：先試上櫃、再試上市
        print(f'🔍 stocks.csv 無紀錄，自動嘗試 {tickers}')
    elif args.market == 'TW':
        tickers = [f'{code}.TW']
    else:
        tickers = [f'{code}.TWO']


    df = None
    for ticker in tickers:
        df = fetch_data(ticker, args.period)
        if df is not None and not df.empty:
            print(f'✅ 資料來源：{ticker}（{len(df)} 筆）')
            break

    if df is None or df.empty:
        print('❌ 無法取得資料，請確認代號與網路連線')
        return

    prices = df['Close']
    current = prices.iloc[-1]
    params = estimate_ou_params(prices)

    theta = params['theta']
    kappa = params['kappa']
    sigma = params['sigma']
    hl = params['half_life_days']
    vol_type = params['vol_type']

    print()
    print(f'=== {code} OU 均值回歸機率預測 ===')
    print(f'現價            ：{current:.1f} 元')
    print(f'均衡價 θ         ：{theta:.1f} 元（長期均值，OU 吸引點）')
    print(f'回歸速度 κ（年化）：{kappa:.2f}')
    print(f'半衰期           ：{hl:.0f} 交易日')
    print(f'年化波動率 σ      ：{sigma:.1f} 元（以 {vol_type} 估計）')
    print(f'偏離均衡          ：{(current - theta) / theta * 100:+.1f}%'
          + (' ─ 偏貴' if current > theta else ' ─ 偏便宜'))

    # 推算或解析目標價
    if args.targets_up:
        t_up = [float(x) for x in args.targets_up.split(',')]
    else:
        t_up, _ = auto_targets(current, step=args.step)

    if args.targets_down:
        t_dn = [float(x) for x in args.targets_down.split(',')]
    else:
        _, t_dn = auto_targets(current, step=args.step)
    t_dn = [x for x in t_dn if x > 0]

    day_list = [int(d) for d in args.days.split(',')]

    for days in day_list:
        print()
        print(f'【未來 {days} 交易日】')
        print('  [上漲機率]')
        for th in t_up:
            _, p_h = monte_carlo_prob(current, 0, th, theta, kappa, sigma,
                                      days=days, n_sims=args.sims)
            bar = '█' * int(p_h * 20)
            print(f'    漲至 {th:>6.0f} 元：{p_h*100:5.1f}%  {bar}')
        print('  [下跌機率]')
        for tl in t_dn:
            p_l, _ = monte_carlo_prob(current, tl, 999999, theta, kappa, sigma,
                                      days=days, n_sims=args.sims)
            bar = '█' * int(p_l * 20)
            print(f'    跌至 {tl:>6.0f} 元：{p_l*100:5.1f}%  {bar}')

    print()
    # 半衰期建議
    if hl < 15:
        print(f'⚡ 快速回歸（{hl:.0f} 日），買回後持有時間不需太長')
    elif hl < 40:
        print(f'✅ 中速回歸（{hl:.0f} 日），滾動策略操作節奏合理')
    else:
        print(f'⚠️ 緩慢回歸（{hl:.0f} 日），建議分批操作，不求一次到位')


if __name__ == '__main__':
    main()
