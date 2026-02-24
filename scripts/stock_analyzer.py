import argparse
import yfinance as yf
import pandas as pd
import datetime
import os
import re

def get_ticker_data(ticker_symbol):
    ticker, history = None, None
    for suffix in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{ticker_symbol}{suffix}")
            h = t.history(period="3mo")
            if h is not None and not h.empty:
                ticker, history = t, h
                break
        except Exception:
            continue

    if history is None or history.empty:
        print(f"無法取得 {ticker_symbol} 的數據。")
        return None, None

    close = history['Close'].dropna()
    if len(close) == 0:
        print(f"{ticker_symbol}: 收盤數據為空")
        return None, None

    current_price = close.iloc[-1]
    ma20 = close.rolling(window=20, min_periods=1).mean().iloc[-1]

    # Simple dividend yield estimate (based on trailing twelve months if available)
    try:
        info = ticker.info
    except Exception:
        info = {}
    dividend_yield = info.get('dividendYield', 'N/A')
    if dividend_yield != 'N/A' and dividend_yield is not None:
        if dividend_yield < 1.0:
            dividend_yield = f"{dividend_yield * 100:.2f}%"
        else:
            dividend_yield = f"{dividend_yield:.2f}%"

    return {
        'price': current_price,
        'ma20': ma20,
        'dividend_yield': dividend_yield
    }, info

def check_stop_loss(current_price, cost_price, ma20):
    alerts = []
    
    if current_price < ma20:
        alerts.append("跌破月線 (20MA)")
        
    loss_pct = (current_price - cost_price) / cost_price
    if loss_pct <= -0.10:
         alerts.append(f"觸及 -10% 停損 (目前損益: {loss_pct*100:.2f}%)")
         
    return alerts

def analyze_trade_files(trades_dir):
    print(f"正在掃描 {trades_dir} 目錄下的交易紀錄...\n")
    if not os.path.exists(trades_dir):
        print("Trades 目錄不存在!")
        return
        
    for filename in os.listdir(trades_dir):
        if not filename.endswith(".md") or filename == "template.md":
            continue
            
        filepath = os.path.join(trades_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        ticker_match = re.search(r'\[標的\].*?(\d{4,6})', content)
        cost_match = re.search(r'買進(?:均)?價[^\d]*([\d,\.]+)', content)
        
        if ticker_match and cost_match:
            ticker = ticker_match.group(1)
            cost = float(cost_match.group(1).replace(',', ''))
            
            print(f"--- 標的: {ticker} (成本: {cost}) ---")
            data, _ = get_ticker_data(ticker)
            if data:
                print(f"現價: {data['price']:.2f}, 20MA: {data['ma20']:.2f}")
                alerts = check_stop_loss(data['price'], cost, data['ma20'])
                if alerts:
                    print("[預警] " + " | ".join(alerts))
                else:
                    print("[正常] 未觸發停損或破月線。")
        else:
            print(f"無法解析 {filename} 中的代號或買進價格，請確認格式。")
        print()

def main():
    parser = argparse.ArgumentParser(description="台股筆記本自動分析工具")
    parser.add_argument('--ticker', type=str, help="指定股票代號 (如 00919)")
    parser.add_argument('--cost', type=float, help="輸入持有成本價進行停損檢查")
    parser.add_argument('--scan-trades', action='store_true', help="掃描 trades 目錄下的所有標的")
    args = parser.parse_args()

    if args.scan_trades:
        # Assuming script is run from s:\股票筆記\scripts or root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        trades_dir = os.path.join(os.path.dirname(current_dir), 'trades')
        analyze_trade_files(trades_dir)
        return

    if args.ticker:
        data, info = get_ticker_data(args.ticker)
        if data:
            print(f"\n[{args.ticker}] 即時資訊")
            print(f"➤ 目前價格: {data['price']:.2f}")
            print(f"➤ 20MA (月線): {data['ma20']:.2f}")
            print(f"➤ 預估殖利率: {data['dividend_yield']}")
            
            if args.cost:
                alerts = check_stop_loss(data['price'], args.cost, data['ma20'])
                print("\n[停損與預警檢查]")
                if alerts:
                    for alert in alerts:
                        print(f"⚠️ {alert}")
                else:
                    print("✅ 狀態正常，未跌破月線或觸及 -10%")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
