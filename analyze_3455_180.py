import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
from scipy.stats import norm
import warnings
warnings.filterwarnings('ignore')

t = '3455.TWO'
session = creq.Session(verify=False, impersonate='chrome')

try:
    df = yf.Ticker(t, session=session).history(period='1y')
    if not df.empty:
        # 1. GBM Parameters
        returns = df['Close'].pct_change().dropna()
        sigma = returns.std() * np.sqrt(252)
        mu = returns.mean() * 252 + 0.5 * (sigma ** 2)
        
        S0 = df['Close'].iloc[-1]
        target = 180.0
        
        def prob_reaching(S0, L, mu, sigma, days):
            T = days / 252.0
            d2 = (np.log(L / S0) - (mu - 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
            # Probability S_T >= L
            prob = 1 - norm.cdf(d2)
            return prob

        horizons = [20, 60, 120, 252]
        probs = {d: prob_reaching(S0, target, mu, sigma, d) for d in horizons}
        
        # 2. Physics Metrics
        price_min = df['Low'].min()
        price_max = df['High'].max()
        bins = np.linspace(price_min, price_max, 11)
        df['bin'] = pd.cut(df['Close'], bins=bins)
        volume_profile = df.groupby('bin')['Volume'].sum()
        avg_vol = df['Volume'].mean()
        curr_vol = df['Volume'].iloc[-5:].mean()
        reynolds = curr_vol / avg_vol
        
        print(f"--- 3455 Analysis ---")
        print(f"Current Price: {S0:.1f}")
        print(f"Drift (mu): {mu*100:.1f}%")
        print(f"Volatility (sigma): {sigma*100:.1f}%")
        print(f"Reynolds Number: {reynolds:.2f}")
        print("\n--- Probabilities of reaching 180.0 ---")
        for d, p in probs.items():
            print(f"Within {d} trading days: {p*100:.1f}%")
            
        print("\n--- Volume Profile (Resistance) ---")
        print(volume_profile.to_string())
        
except Exception as e:
    print(f"Error: {e}")
