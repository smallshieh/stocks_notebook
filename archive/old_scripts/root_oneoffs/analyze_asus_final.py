import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
import warnings
warnings.filterwarnings('ignore')

t = '2357.TW'
session = creq.Session(verify=False, impersonate='chrome')

try:
    df = yf.Ticker(t, session=session).history(period='1y')
    if not df.empty:
        # GBM
        returns = df['Close'].pct_change().dropna()
        sigma = returns.std() * np.sqrt(252)
        mu = returns.mean() * 252 + 0.5 * (sigma ** 2)
        
        # Physics
        price_min = df['Low'].min()
        price_max = df['High'].max()
        bins = np.linspace(price_min, price_max, 11)
        df['bin'] = pd.cut(df['Close'], bins=bins)
        volume_profile = df.groupby('bin')['Volume'].sum()
        avg_vol = df['Volume'].mean()
        curr_vol = df['Volume'].iloc[-5:].mean()
        reynolds = curr_vol / avg_vol
        
        print(f"PRICE: {df['Close'].iloc[-1]:.1f}")
        print(f"MU: {mu*100:.1f}%")
        print(f"SIGMA: {sigma*100:.1f}%")
        print(f"REYNOLDS: {reynolds:.2f}")
        print(f"VOLUME_PROFILE:")
        print(volume_profile.to_string())
        
        # Calculate 20-day probabilities manually
        current_price = df['Close'].iloc[-1]
        t_20 = 20/252
        expected_price = current_price * np.exp(mu * t_20)
        print(f"EXPECTED_20D: {expected_price:.1f}")
except Exception as e:
    print(f"Error: {e}")
