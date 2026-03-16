import pandas as pd
import numpy as np
import yfinance as yf
from curl_cffi import requests as creq
import warnings
warnings.filterwarnings('ignore')

t = '2357.TW'
session = creq.Session(verify=False, impersonate='chrome')

try:
    df = yf.Ticker(t, session=session).history(period='6mo')
    if not df.empty:
        closes = df['Close']
        y = closes.values[1:]
        x = closes.values[:-1]
        
        # Linear Regression: y = b*x + a
        b, a = np.polyfit(x, y, 1)
        
        dt = 1/252
        kappa = -np.log(b) / dt
        theta = a / (1 - b)
        half_life = np.log(2) / kappa
        
        # Volatility estimation from residuals
        residuals = y - (b * x + a)
        sigma = np.std(residuals) * np.sqrt(252)
        
        print(f"Current Price: {closes.iloc[-1]:.1f}")
        print(f"Mean Price (Theta): {theta:.1f}")
        print(f"Reversion Speed (Kappa): {kappa:.4f}")
        print(f"Half-life (Days): {half_life * 252:.1f}")
        print(f"Residual Sigma: {sigma:.1f}")
        
except Exception as e:
    print(f"Error: {e}")
