import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
from scipy.stats import norm
import warnings
warnings.filterwarnings('ignore')

t = '3037.TW'
session = creq.Session(verify=False, impersonate='chrome')

try:
    df = yf.Ticker(t, session=session).history(period='1y')
    if not df.empty:
        # 1. GBM Parameters
        returns = df['Close'].pct_change().dropna()
        sigma = returns.std() * np.sqrt(252)
        mu = returns.mean() * 252 + 0.5 * (sigma ** 2)
        
        S0 = df['Close'].iloc[-1]
        
        def prob_reaching(S0, L, mu, sigma, days):
            T = days / 252.0
            d2 = (np.log(L / S0) - (mu - 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
            prob = 1 - norm.cdf(d2)
            return prob

        # Target 1: +10%, Target 2: +20%
        target1 = S0 * 1.10
        target2 = S0 * 1.20
        
        horizons = [20, 60]
        p1_20 = prob_reaching(S0, target1, mu, sigma, 20)
        p2_60 = prob_reaching(S0, target2, mu, sigma, 60)
        
        # 2. Physics Metrics
        price_min = df['Low'].min()
        price_max = df['High'].max()
        bins = np.linspace(price_min, price_max, 11)
        df['bin'] = pd.cut(df['Close'], bins=bins)
        volume_profile = df.groupby('bin')['Volume'].sum()
        avg_vol = df['Volume'].mean()
        curr_vol = df['Volume'].iloc[-5:].mean()
        reynolds = curr_vol / avg_vol
        
        print(f"--- 3037 Analysis ---")
        print(f"Current Price: {S0:.1f}")
        print(f"Drift (mu): {mu*100:.1f}%")
        print(f"Volatility (sigma): {sigma*100:.1f}%")
        print(f"Reynolds Number: {reynolds:.2f}")
        print(f"\nProb of +10% ({target1:.1f}) in 20 days: {p1_20*100:.1f}%")
        print(f"Prob of +20% ({target2:.1f}) in 60 days: {p2_60*100:.1f}%")
            
        print("\n--- Volume Profile (Resistance) ---")
        print(volume_profile.to_string())
        
except Exception as e:
    print(f"Error: {e}")
