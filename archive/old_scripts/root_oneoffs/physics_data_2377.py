import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
import warnings
warnings.filterwarnings('ignore')

t = '2377.TW'
session = creq.Session(verify=False, impersonate='chrome')

try:
    df = yf.Ticker(t, session=session).history(period='1y')
    if not df.empty:
        # Calculate Volume Profile (10 bins)
        price_min = df['Low'].min()
        price_max = df['High'].max()
        bins = np.linspace(price_min, price_max, 11)
        df['bin'] = pd.cut(df['Close'], bins=bins)
        volume_profile = df.groupby('bin')['Volume'].sum()
        
        # Calculate Volatility (Temperature)
        returns = df['Close'].pct_change().dropna()
        vol = returns.std() * np.sqrt(252)
        
        # Calculate Recent Volume Trend (Reynolds)
        avg_vol = df['Volume'].mean()
        curr_vol = df['Volume'].iloc[-5:].mean()
        reynolds = curr_vol / avg_vol
        
        print(f"--- Volume Profile ---")
        print(volume_profile)
        print(f"\n--- Metrics ---")
        print(f"Current Price: {df['Close'].iloc[-1]}")
        print(f"Volatility (Sigma): {vol:.4f}")
        print(f"Reynolds (Vol Ratio): {reynolds:.2f}")
        
except Exception as e:
    print(f"Error: {e}")
