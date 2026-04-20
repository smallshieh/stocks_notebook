"""
watchlist_update_batch.py — 批次計算 watchlist 標的的現價 / 月線 / GBM
- 與 gbm_analysis.py 相容：±1σ / ±1.5σ 目標，Monte Carlo 觸及機率
- 以 numpy 向量化加速（每檔 30,000 路徑一次算完）
"""
import sys
import os
import json
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
from curl_cffi import requests as creq
import yfinance as yf

WATCHLIST_DIR = 's:/股票筆記/watchlist'
N_SIMS = 30000

def load_tickers():
    df = pd.read_csv('s:/股票筆記/stocks.csv', dtype={'code': str})
    df = df.set_index('code')
    out = []
    for fn in sorted(os.listdir(WATCHLIST_DIR)):
        if not fn.endswith('.md') or fn == 'template.md':
            continue
        code = fn.split('_')[0]
        if code in df.index:
            out.append((code, df.loc[code, 'ticker'], df.loc[code, 'name'], fn))
    return out

def fetch(ticker, period='1y'):
    session = creq.Session(verify=False, impersonate='chrome')
    df = yf.Ticker(ticker, session=session).history(period=period)
    df.columns = [c.lower() for c in df.columns]
    return df[['close']].rename(columns={'close': 'Close'}).dropna()

def gbm_params(prices):
    log_r = np.diff(np.log(prices.values))
    sigma_d = np.std(log_r, ddof=1)
    sigma_a = sigma_d * math.sqrt(252)
    mu_d = np.mean(log_r)
    mu_a = (mu_d + 0.5 * sigma_d**2) * 252
    try:
        from arch import arch_model
        am = arch_model(log_r * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
        res = am.fit(disp='off')
        last_cv = res.conditional_volatility.iloc[-1] / 100
        sigma_a = last_cv * math.sqrt(252)
        vol_type = 'GARCH'
    except Exception:
        vol_type = 'Hist'
    return mu_a, sigma_a, vol_type

def mc_touch_prob(S0, mu, sigma, days, targets_up, targets_dn, n_sims=N_SIMS, seed=42):
    """向量化 Monte Carlo。回傳 (targets_up, up_probs, targets_dn, dn_probs)。"""
    rng = np.random.default_rng(seed)
    dt = 1/252
    drift = (mu - 0.5 * sigma**2) * dt
    vol = sigma * math.sqrt(dt)
    # shape (n_sims, days)
    shocks = rng.standard_normal((n_sims, days))
    daily_log = drift + vol * shocks
    cum = np.cumsum(daily_log, axis=1)
    paths = S0 * np.exp(cum)  # (n_sims, days)
    path_max = paths.max(axis=1)
    path_min = paths.min(axis=1)

    up_probs = [float(np.mean(path_max >= th)) for th in targets_up]
    dn_probs = [float(np.mean(path_min <= th)) for th in targets_dn]
    return up_probs, dn_probs

def projection(S0, mu, sigma, days):
    T = days / 252
    std = sigma * math.sqrt(T)
    plus1 = S0 * math.exp(std)
    plus15 = S0 * math.exp(1.5 * std)
    minus1 = S0 * math.exp(-std)
    minus15 = S0 * math.exp(-1.5 * std)
    up_p, dn_p = mc_touch_prob(S0, mu, sigma, days,
                                [plus1, plus15], [minus1, minus15])
    expected = S0 * math.exp(mu * T)
    return {
        'expected': expected,
        '+1sigma_price': plus1, '+1sigma_p': up_p[0],
        '+1.5sigma_price': plus15, '+1.5sigma_p': up_p[1],
        '-1sigma_price': minus1, '-1sigma_p': dn_p[0],
        '-1.5sigma_price': minus15, '-1.5sigma_p': dn_p[1],
    }

def main():
    results = []
    for code, ticker, name, fn in load_tickers():
        try:
            df = fetch(ticker, '1y')
            if df.empty or len(df) < 30:
                results.append({'code': code, 'name': name, 'ticker': ticker, 'file': fn, 'error': f'insufficient ({len(df)})'})
                continue
            prices = df['Close']
            current = float(prices.iloc[-1])
            ma20 = float(prices.iloc[-20:].mean()) if len(prices) >= 20 else None
            ma60 = float(prices.iloc[-60:].mean()) if len(prices) >= 60 else None
            last_date = df.index[-1].strftime('%Y-%m-%d')
            mu, sigma, vt = gbm_params(prices)
            p20 = projection(current, mu, sigma, 20)
            p60 = projection(current, mu, sigma, 60)
            p120 = projection(current, mu, sigma, 120)
            results.append({
                'code': code, 'name': name, 'ticker': ticker, 'file': fn,
                'current': round(current, 2),
                'ma20': round(ma20, 2) if ma20 else None,
                'ma60': round(ma60, 2) if ma60 else None,
                'last_date': last_date,
                'mu': round(mu * 100, 1),
                'sigma': round(sigma * 100, 1),
                'sigma_src': vt,
                'p20': {k: round(v, 4) if isinstance(v, float) else v for k, v in p20.items()},
                'p60': {k: round(v, 4) if isinstance(v, float) else v for k, v in p60.items()},
                'p120': {k: round(v, 4) if isinstance(v, float) else v for k, v in p120.items()},
            })
            print(f'✅ {code} {name}: {current:.2f} | μ={mu*100:+.1f}% σ={sigma*100:.1f}% ({vt})')
        except Exception as e:
            results.append({'code': code, 'name': name, 'ticker': ticker, 'file': fn, 'error': str(e)})
            print(f'❌ {code} {name}: {e}')

    out_path = 's:/股票筆記/scripts/_watchlist_update_data.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'\n→ saved {out_path} ({len(results)})')

if __name__ == '__main__':
    main()
