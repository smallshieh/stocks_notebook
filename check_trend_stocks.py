import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
import warnings
warnings.filterwarnings('ignore')

tickers = [
    '2317.TW', '2330.TW', '6488.TWO', '8069.TWO', '5483.TWO',
    '1210.TW', '1503.TW', '2002.TW', '2357.TW', '2379.TW', '2382.TW', 
    '2454.TW', '2886.TW', '3034.TW', '3231.TW', '4938.TW', '6239.TW'
]

results = []
session = creq.Session(verify=False, impersonate='chrome')

def get_mu(df):
    closes = df['Close']
    if isinstance(closes, pd.DataFrame):
        closes = closes.iloc[:, 0]
    returns = closes.pct_change().dropna()
    sigma = returns.std() * np.sqrt(252)
    mu = returns.mean() * 252 + 0.5 * (sigma ** 2)
    return mu, sigma

for t in tickers:
    try:
        df = yf.Ticker(t, session=session).history(period='1y')
        if not df.empty and len(df) > 200:
            mu, sigma = get_mu(df)
            results.append({'Stock': t.replace('.TW', '').replace('.TWO', ''), 'Drift (mu)': f"+{mu*100:.1f}%" if mu > 0 else f"{mu*100:.1f}%", 'Volatility (sigma)': f"{sigma*100:.1f}%", 'mu_raw': mu})
        else:
            print(f"{t}: not enough data")
    except Exception as e:
        print(f"{t}: Error {e}")

res_df = pd.DataFrame(results).sort_values('mu_raw', ascending=False).drop(columns=['mu_raw'])
print("\n📋 您的持股趨勢排名 (以1年期 μ 漂移率排序)：\n")
print(res_df.to_string(index=False))
