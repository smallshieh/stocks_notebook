"""
物理引擎模組 (Physics Engine)
=============================
將 OHLCV 金融數據映射為經濟物理學變數，提供動量、動能、雷諾數等診斷。

參考：《股市動力學與流體模型：經濟物理學分析框架 v1.2》

變數對應：
  - 質量 m = 成交量 (Volume)
  - 速度 v = 日報酬率 (Daily Return)
  - 動量 p = m × v
  - 動能 KE = ½ × m × v²
  - 加速度 a = Δv / Δt
  - 溫度 T = 20 日波動率 (Rolling Std of Returns)
  - 雷諾數 Re = (m × |v| × L) / η
    其中 L = 日內價格振幅 (High - Low)，η = 20 日平均成交量（流動性代理）
"""

import pandas as pd
import numpy as np


def compute_physics(df: pd.DataFrame) -> pd.DataFrame:
    """
    對 OHLCV DataFrame 計算物理量。

    參數:
        df: 包含 'Open', 'High', 'Low', 'Close', 'Volume' 欄位的 DataFrame

    回傳:
        附加物理量欄位的 DataFrame
    """
    result = df.copy()

    # 速度 v：日報酬率
    result['velocity'] = result['Close'].pct_change()

    # 質量 m：成交量
    result['mass'] = result['Volume']

    # 動量 p = m × v
    result['momentum'] = result['mass'] * result['velocity']

    # 動能 KE = ½ × m × v²
    result['kinetic_energy'] = 0.5 * result['mass'] * result['velocity'] ** 2

    # 加速度 a = Δv（速度的差分）
    result['acceleration'] = result['velocity'].diff()

    # 溫度 T：20 日報酬率滾動標準差（波動率）
    result['temperature'] = result['velocity'].rolling(window=20, min_periods=5).std()

    # 雷諾數 Re = (m × |v| × L) / η
    # L = 日內振幅, η = 20 日平均成交量（流動性代理）
    result['price_range'] = result['High'] - result['Low']  # 特徵長度 L
    result['liquidity'] = result['Volume'].rolling(window=20, min_periods=5).mean()  # η
    result['reynolds'] = (
        result['mass'] * result['velocity'].abs() * result['price_range']
    ) / result['liquidity'].replace(0, np.nan)

    return result


def diagnose_fluid_state(row: pd.Series) -> str:
    """
    根據單日物理量判斷流體狀態。

    回傳格式：emoji + 狀態描述
    """
    v = row.get('velocity', 0) or 0
    m = row.get('mass', 0) or 0
    ke = row.get('kinetic_energy', 0) or 0
    re = row.get('reynolds', 0) or 0
    temp = row.get('temperature', 0) or 0

    # 雷諾數判斷
    if re > 2000:
        turbulence = '湍流'
        turb_emoji = '🔴'
    elif re > 1000:
        turbulence = '過渡區'
        turb_emoji = '🟡'
    else:
        turbulence = '層流'
        turb_emoji = '🟢'

    # 價量關係判斷
    if v > 0 and m > 0:
        if row.get('acceleration', 0) and row['acceleration'] > 0:
            state = '加速推進（價漲量增，健康）'
        else:
            state = '慣性滑行（價漲，動力待觀察）'
    elif v < 0 and m > 0:
        state = '減速下墜（價跌）'
    else:
        state = '靜止（無明顯方向）'

    return f"{turb_emoji} {turbulence}｜{state}"


def detect_antigravity(df: pd.DataFrame, lookback: int = 3) -> bool:
    """
    反重力偵測：股價上漲但成交量連續萎縮 ≥ lookback 日。
    代表缺乏動力支撐的慣性滑行，是趨勢衰竭的預兆。

    回傳:
        True = 觸發反重力預警
    """
    if len(df) < lookback + 1:
        return False

    recent = df.tail(lookback + 1)

    # 檢查價格是否上漲
    price_rising = recent['Close'].iloc[-1] > recent['Close'].iloc[-(lookback + 1)]

    # 檢查成交量是否連續萎縮
    volumes = recent['Volume'].values[1:]  # 取最近 lookback 日
    volume_shrinking = all(volumes[i] < volumes[i - 1] for i in range(1, len(volumes)))

    return price_rising and volume_shrinking


def detect_energy_dissipation(df: pd.DataFrame, lookback: int = 3) -> bool:
    """
    能量耗散偵測：動能連續下降但價格維持高位（放量不漲）。
    代表輸入的能量被摩擦生熱消耗，系統即將冷卻。

    回傳:
        True = 觸發能量耗散預警
    """
    if len(df) < lookback + 1:
        return False

    recent = df.tail(lookback)

    # 動能連續下降
    ke_values = recent['kinetic_energy'].dropna().values
    if len(ke_values) < lookback:
        return False
    ke_declining = all(ke_values[i] < ke_values[i - 1] for i in range(1, len(ke_values)))

    # 價格維持高位（振幅小於 2%）
    price_range_pct = (recent['Close'].max() - recent['Close'].min()) / recent['Close'].mean()
    price_flat = price_range_pct < 0.02

    return ke_declining and price_flat


def generate_physics_report(df: pd.DataFrame, ticker: str) -> str:
    """
    生成完整的物理診斷報告文字。

    參數:
        df: 已計算物理量的 DataFrame
        ticker: 股票代號

    回傳:
        格式化的診斷報告字串
    """
    if df is None or df.empty:
        return f"[{ticker}] 無法生成物理診斷：資料不足"

    # 計算物理量
    physics_df = compute_physics(df)
    latest = physics_df.iloc[-1]
    prev = physics_df.iloc[-2] if len(physics_df) >= 2 else None

    lines = []
    lines.append(f"\n[{ticker}] 物理診斷")
    lines.append("─" * 40)

    # 動量
    p = latest.get('momentum', 0) or 0
    p_dir = "正向 ↑" if p > 0 else "負向 ↓" if p < 0 else "中性"
    lines.append(f"➤ 動量 p: {p:+,.0f} ({p_dir})")

    # 動能
    ke = latest.get('kinetic_energy', 0) or 0
    ke_change = ""
    if prev is not None:
        prev_ke = prev.get('kinetic_energy', 0) or 0
        if prev_ke > 0:
            ke_pct = (ke - prev_ke) / prev_ke * 100
            ke_change = f"，較前日 {ke_pct:+.1f}%"
    lines.append(f"➤ 動能 KE: {ke:,.0f}{ke_change}")

    # 系統溫度（波動率）
    temp = latest.get('temperature', 0) or 0
    temp_status = "🟢 正常" if temp < 0.03 else "🟡 偏高" if temp < 0.05 else "🔴 過熱"
    lines.append(f"➤ 系統溫度 T: {temp * 100:.2f}% ({temp_status})")

    # 雷諾數
    re = latest.get('reynolds', 0) or 0
    re_status = "🟢 層流" if re < 1000 else "🟡 過渡區" if re < 2000 else "🔴 湍流"
    lines.append(f"➤ 雷諾數 Re: {re:,.0f} ({re_status})")

    # 動能趨勢（近 5 日）
    recent_ke = physics_df['kinetic_energy'].dropna().tail(5)
    if len(recent_ke) >= 3:
        ke_trend_up = all(recent_ke.iloc[i] >= recent_ke.iloc[i - 1] for i in range(1, len(recent_ke)))
        ke_trend_down = all(recent_ke.iloc[i] <= recent_ke.iloc[i - 1] for i in range(1, len(recent_ke)))
        if ke_trend_up:
            lines.append(f"➤ 動能趨勢: 連續 {len(recent_ke)} 日上升 ✅")
        elif ke_trend_down:
            lines.append(f"➤ 動能趨勢: 連續 {len(recent_ke)} 日下降 ⚠️")
        else:
            lines.append(f"➤ 動能趨勢: 震盪")

    # 流體狀態
    fluid = diagnose_fluid_state(latest)
    lines.append(f"➤ 流體狀態: {fluid}")

    # 反重力預警
    if detect_antigravity(physics_df):
        lines.append("⚠️ 反重力預警：價漲量縮 ≥ 3 日，慣性滑行中，缺乏動力支持")

    # 能量耗散預警
    if detect_energy_dissipation(physics_df):
        lines.append("⚠️ 能量耗散：動能連降但價格持平，系統過熱冷卻中")

    lines.append("")
    return "\n".join(lines)
