import os
import argparse
import pandas as pd
import datetime
import re

# === SSL 修復 ===
# yfinance 1.2.0 起改用 curl_cffi，不接受 requests.Session。
# 若 certifi 路徑含中文，curl_cffi 會找不到 CA 檔，改指向 ASCII 備份路徑。
_FALLBACK_CERT = r"C:\Users\smallshieh\cacert.pem"
try:
    import certifi as _certifi
    _cert_path = _certifi.where()
    if not all(ord(c) < 128 for c in _cert_path) and os.path.exists(_FALLBACK_CERT):
        _cert_path = _FALLBACK_CERT
    os.environ["CURL_CA_BUNDLE"] = _cert_path
    os.environ.setdefault("SSL_CERT_FILE", _cert_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _cert_path)
except ImportError:
    pass

# === 資料源載入 ===
import yfinance as yf

# === 證交所 / 櫃買中心直連 API（fallback 資料源）===
import ssl
import urllib.request
import json
import time


def _parse_number(s):
    """清理證交所/櫃買中心回傳的數值字串（移除逗號、處理空值）"""
    if not s or s == '--' or s == '':
        return None
    return float(str(s).replace(',', ''))


def _fetch_twse_month(ticker_symbol, year, month):
    """
    從 TWSE（上市）取得指定月份的日成交資料。
    API: https://www.twse.com.tw/exchangeReport/STOCK_DAY
    欄位: ['日期', '成交股數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌價差', '成交筆數']
    """
    ctx = ssl._create_unverified_context()
    date_str = f"{year}{month:02d}01"
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={ticker_symbol}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))

    if data.get('stat') != 'OK' or not data.get('data'):
        return []

    rows = []
    for row in data['data']:
        # 日期格式：115/02/03（民國年），轉為西元
        date_parts = row[0].split('/')
        y = int(date_parts[0]) + 1911
        m = int(date_parts[1])
        d = int(date_parts[2])

        o = _parse_number(row[3])  # 開盤價
        h = _parse_number(row[4])  # 最高價
        lo = _parse_number(row[5])  # 最低價
        c = _parse_number(row[6])  # 收盤價
        vol = _parse_number(row[1])  # 成交股數

        if c is not None:
            rows.append({
                'Date': datetime.datetime(y, m, d),
                'Open': o, 'High': h, 'Low': lo, 'Close': c,
                'Volume': vol / 1000 if vol else 0,  # 股 → 張
            })
    return rows


def _fetch_tpex_month(ticker_symbol, year, month):
    """
    從 TPEX（上櫃/櫃買中心）取得指定月份的日成交資料。
    API: https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes
    """
    ctx = ssl._create_unverified_context()
    date_str = f"{year}/{month:02d}/01"
    url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={date_str}&id={ticker_symbol}&response=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))

    tables = data.get('tables', [])
    if not tables or not tables[0].get('data'):
        return []

    rows = []
    for row in tables[0]['data']:
        # 日期格式：115/02/03（民國年）
        date_parts = str(row[0]).split('/')
        y = int(date_parts[0]) + 1911
        m = int(date_parts[1])
        d = int(date_parts[2])

        c = _parse_number(row[2])   # 收盤價
        o = _parse_number(row[4])   # 開盤價
        h = _parse_number(row[5])   # 最高價
        lo = _parse_number(row[6])  # 最低價
        vol = _parse_number(row[8]) # 成交股數

        if c is not None:
            rows.append({
                'Date': datetime.datetime(y, m, d),
                'Open': o, 'High': h, 'Low': lo, 'Close': c,
                'Volume': vol / 1000 if vol else 0,  # 股 → 張
            })
    return rows


def _fetch_via_twse_api(ticker_symbol):
    """
    直連 TWSE / TPEX API 取得近 3 個月歷史資料（fallback 用）。
    自動判斷上市/上櫃，回傳與 yfinance 格式相同的 DataFrame。
    """
    try:
        today = datetime.date.today()
        all_rows = []

        # 抓取近 3 個月（當月 + 前 2 個月）
        for offset in [2, 1, 0]:
            y = today.year
            m = today.month - offset
            if m <= 0:
                m += 12
                y -= 1

            # 先試 TWSE（上市），失敗再試 TPEX（上櫃）
            rows = _fetch_twse_month(ticker_symbol, y, m)
            if not rows:
                time.sleep(0.5)  # 避免請求過快
                rows = _fetch_tpex_month(ticker_symbol, y, m)

            all_rows.extend(rows)
            if offset > 0:
                time.sleep(1)  # 證交所有請求頻率限制

        if not all_rows:
            return None, None

        df = pd.DataFrame(all_rows)
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)

        close = df['Close'].dropna()
        current_price = close.iloc[-1]
        ma20 = close.rolling(window=20, min_periods=1).mean().iloc[-1]

        result = {
            'price': current_price,
            'ma20': ma20,
            'dividend_yield': 'N/A（證交所 API）',
        }

        return result, df

    except Exception as e:
        print(f"[TWSE/TPEX fallback] 取得 {ticker_symbol} 失敗: {e}")
        return None, None


def get_ticker_data(ticker_symbol):
    """
    取得股票資料。優先使用 yfinance，失敗時 fallback 至 twstock。
    回傳：(data_dict, info_dict, history_df) 或 (None, None, None)
    """
    # === 第一優先：yfinance ===
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

    if history is not None and not history.empty:
        close = history['Close'].dropna()
        if len(close) == 0:
            print(f"{ticker_symbol}: 收盤數據為空")
            return None, None, None

        current_price = close.iloc[-1]
        ma20 = close.rolling(window=20, min_periods=1).mean().iloc[-1]

        # 殖利率
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
        }, info, history

    # === 第二優先：證交所 / 櫃買中心 API fallback ===
    print(f"[yfinance] {ticker_symbol} 取得失敗，嘗試證交所 API...")
    tw_data, tw_history = _fetch_via_twse_api(ticker_symbol)
    if tw_data is not None:
        print(f"[fallback] 使用證交所/櫃買中心 API ✅")
        return tw_data, {}, tw_history

    print(f"無法取得 {ticker_symbol} 的數據。")
    return None, None, None


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
            data, _, _ = get_ticker_data(ticker)
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
    parser.add_argument('--ticker', type=str, nargs='+', help="指定股票代號 (如 00919)，可指定多個")
    parser.add_argument('--cost', type=float, help="輸入持有成本價進行停損檢查")
    parser.add_argument('--scan-trades', action='store_true', help="掃描 trades 目錄下的所有標的")
    parser.add_argument('--physics', action='store_true', help="執行經濟物理模型診斷（動量、動能、雷諾數）")
    parser.add_argument('--quantile', action='store_true', help="執行歷史分位數決策診斷（賣出/買回/暫停區）")
    args = parser.parse_args()

    if args.scan_trades:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        trades_dir = os.path.join(os.path.dirname(current_dir), 'trades')
        analyze_trade_files(trades_dir)
        return

    if args.ticker:
        for ticker_symbol in args.ticker:
            data, info, history = get_ticker_data(ticker_symbol)
            if data:
                print(f"\n[{ticker_symbol}] 即時資訊")
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

                # 物理診斷模式
                if args.physics and history is not None:
                    from physics_engine import generate_physics_report
                    report = generate_physics_report(history, ticker_symbol)
                    print(report)

                # 歷史分位數診斷模式
                if args.quantile and history is not None:
                    from quantile_engine import generate_quantile_report
                    q_report = generate_quantile_report(history, ticker_symbol)
                    print(q_report)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
