"""
dashboard.py — 股票筆記 Web Dashboard
啟動方式：.venv/Scripts/streamlit.exe run scripts/dashboard.py
"""
import sys
import os
import re
import glob

sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_CSV = os.path.join(BASE_DIR, 'portfolio_history.csv')
TRADES_DIR  = os.path.join(BASE_DIR, 'trades')


# ── 資料載入 ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_history():
    df = pd.read_csv(HISTORY_CSV, parse_dates=['date'])
    df = df.dropna(subset=['total_portfolio_value'])
    df = df.sort_values('date')
    return df


@st.cache_data(ttl=300)
def load_latest_checkup():
    """讀取最新一份持倉健診 MD，解析成 DataFrame。"""
    pattern = os.path.join(BASE_DIR, '持倉健診_*.md')
    files = sorted(glob.glob(pattern))
    if not files:
        return None, None, None, None
    latest = files[-1]
    report_date = re.search(r'持倉健診_(\d{4}-\d{2}-\d{2})', latest)
    report_date = report_date.group(1) if report_date else '未知'

    with open(latest, 'r', encoding='utf-8') as f:
        content = f.read()

    rows = []
    # 解析 MD 表格列（跳過 header 和分隔線）
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith('|') or '---' in line:
            continue
        cells = [c.strip() for c in line.split('|') if c.strip()]
        # 持倉表有 7 欄：代碼 名稱 現價 20MA 損益% 殖利率 狀態
        if len(cells) == 7 and cells[0] not in ('代碼', '桶別'):
            code  = cells[0].strip('`')
            name  = cells[1]
            try:
                price = float(cells[2])
            except:
                continue
            try:
                ma20 = float(cells[3])
            except:
                ma20 = None
            pct_str = cells[4].replace('%', '').replace('+', '')
            try:
                pct = float(pct_str)
            except:
                pct = None
            dy    = cells[5]
            status = cells[6]
            is_alert = '⚠️' in status
            rows.append({
                '代碼': code, '名稱': name, '現價': price,
                '20MA': ma20, '損益%': pct, '殖利率': dy,
                '狀態': status, '預警': is_alert,
            })

    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    # 解析資金桶
    buckets = {}
    bucket_pattern = re.compile(
        r'\|\s*(Core|Tactical)[^\|]*\|\s*([\d,]+)\s*\|\s*([\d.]+)%'
    )
    for m in bucket_pattern.finditer(content):
        buckets[m.group(1)] = {
            'value': float(m.group(2).replace(',', '')),
            'pct':   float(m.group(3)),
        }

    return df, buckets, report_date, latest


# ── 頁面設定 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title='股票筆記 Dashboard',
    page_icon='📊',
    layout='wide',
)

st.title('📊 股票筆記 Dashboard')

# ── 載入資料 ──────────────────────────────────────────────────────────────────
hist = load_history()
holdings_df, buckets, report_date, checkup_file = load_latest_checkup()

# ── 頂部 KPI 卡片 ─────────────────────────────────────────────────────────────
st.subheader(f'持倉健診：{report_date}')

if not hist.empty:
    latest_row   = hist.iloc[-1]
    prev_row     = hist.iloc[-2] if len(hist) >= 2 else latest_row
    portfolio_val = latest_row['total_portfolio_value']
    stock_val     = latest_row['total_stock_value']
    cash_val      = latest_row.get('cash_balance', 0) or 0
    daily_chg     = portfolio_val - prev_row['total_portfolio_value']
    base_val      = hist.iloc[0]['total_portfolio_value']
    total_return  = (portfolio_val - base_val) / base_val * 100

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric('總淨值', f'{portfolio_val:,.0f}', f'{daily_chg:+,.0f}')
    col2.metric('股票市值', f'{stock_val:,.0f}')
    col3.metric('現金餘額', f'{cash_val:,.0f}')
    col4.metric('累計報酬', f'{total_return:+.1f}%',
                delta_color='normal' if total_return >= 0 else 'inverse')
    # 預警數
    if holdings_df is not None and not holdings_df.empty:
        alert_count = holdings_df['預警'].sum()
        col5.metric('⚠️ 預警標的', int(alert_count))

# ── 淨值走勢圖 ────────────────────────────────────────────────────────────────
st.divider()
col_left, col_right = st.columns([3, 1])

with col_left:
    st.subheader('淨值走勢')
    if not hist.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist['date'], y=hist['total_portfolio_value'],
            mode='lines+markers', name='總淨值',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=6),
            hovertemplate='%{x|%Y-%m-%d}<br>淨值：%{y:,.0f}<extra></extra>',
        ))
        fig.add_trace(go.Bar(
            x=hist['date'], y=hist['cash_inflow'],
            name='現金流入', marker_color='rgba(0,200,100,0.5)',
            hovertemplate='%{x|%Y-%m-%d}<br>流入：%{y:,.0f}<extra></extra>',
            yaxis='y2',
        ))
        fig.update_layout(
            height=320,
            yaxis=dict(title='淨值（元）', tickformat=',.0f'),
            yaxis2=dict(title='現金流入', overlaying='y', side='right', tickformat=',.0f'),
            legend=dict(orientation='h', y=1.02),
            margin=dict(l=10, r=10, t=10, b=10),
            hovermode='x unified',
        )
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader('資金桶分配')
    if buckets:
        labels = list(buckets.keys())
        values = [buckets[k]['value'] for k in labels]
        colors = ['#2196F3', '#FF9800']
        fig_pie = px.pie(
            names=labels, values=values,
            color_discrete_sequence=colors,
            hole=0.4,
        )
        fig_pie.update_traces(
            textinfo='label+percent',
            hovertemplate='%{label}<br>市值：%{value:,.0f}<br>佔比：%{percent}<extra></extra>',
        )
        fig_pie.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        for k, v in buckets.items():
            target = 50 if k == 'Core' else 30
            diff = v['pct'] - target
            icon = '✅' if abs(diff) < 10 else '⚠️'
            st.caption(f"{icon} {k}：{v['pct']:.1f}%（目標 {target}%，{diff:+.1f}%）")
    else:
        st.info('無資金桶資料')

# ── 持倉總覽表 ────────────────────────────────────────────────────────────────
st.divider()
st.subheader('持倉總覽')

if holdings_df is not None and not holdings_df.empty:
    # 篩選器
    filter_col1, filter_col2 = st.columns([1, 3])
    with filter_col1:
        only_alert = st.checkbox('只看預警標的', value=False)
    with filter_col2:
        sort_by = st.selectbox('排序依據', ['損益%', '現價', '代碼'], index=0)

    display_df = holdings_df.copy()
    if only_alert:
        display_df = display_df[display_df['預警']]

    display_df = display_df.sort_values(sort_by, ascending=(sort_by == '代碼'))

    # 顏色標示
    def highlight_row(row):
        if row['預警']:
            return ['background-color: #fff3cd'] * len(row)
        return [''] * len(row)

    def color_pct(val):
        if val is None:
            return ''
        if val >= 10:
            return 'color: green; font-weight: bold'
        if val <= -10:
            return 'color: red; font-weight: bold'
        if val < 0:
            return 'color: #c0392b'
        return 'color: #27ae60'

    show_cols = ['代碼', '名稱', '現價', '20MA', '損益%', '殖利率', '狀態']
    style_cols = show_cols + ['預警']
    styled = (
        display_df[style_cols]
        .style
        .apply(highlight_row, axis=1)
        .map(color_pct, subset=['損益%'])
        .format({'現價': '{:.2f}', '20MA': '{:.2f}', '損益%': '{:+.1f}%'}, na_rep='—')
        .hide(axis='columns', subset=['預警'])
    )
    st.dataframe(styled, use_container_width=True, height=550)

    alert_df = holdings_df[holdings_df['預警']]
    if not alert_df.empty:
        st.subheader('⚠️ 預警標的摘要')
        for _, row in alert_df.iterrows():
            st.error(f"**{row['代碼']} {row['名稱']}** — {row['狀態']}　損益 {row['損益%']:+.1f}%　現價 {row['現價']:.2f}")

else:
    st.info('找不到健診報告，請先執行 portfolio_report.py')

# ── 底部資訊 ──────────────────────────────────────────────────────────────────
st.divider()
if checkup_file:
    st.caption(f'健診來源：{os.path.basename(checkup_file)}')
st.caption('重新整理：按 R 或點左上角 ⟳')
