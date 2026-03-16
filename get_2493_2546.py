import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
import warnings
warnings.filterwarnings('ignore')

tickers = ['2493.TW', '2546.TW']
session = creq.Session(verify=False, impersonate='chrome')

for t in tickers:
    try:
        df = yf.Ticker(t, session=session).history(period='1y')
        if not df.empty:
            closes = df['Close']
            returns = closes.pct_change().dropna()
            sigma = returns.std() * np.sqrt(252)
            mu = returns.mean() * 252 + 0.5 * (sigma ** 2)
            print(f'{t} | MU: {mu*100:.1f}%, SIGMA: {sigma*100:.1f}%')
    except Exception as e:
        print(f'{t} | error: {e}')
