"""
event_detector.py — Layer 3 事件偵測器
========================================
在 wave_score_scan.py 之後執行，比對當日資料與前次狀態，
輸出「值得觸發 model refresh」的事件至 scan.log。

事件分類（閾值型）：
  NEAR_TARGET  — 現價 ≥ 目標價 × 97%（接近波段倉減持觸發點）
  NEAR_STOP    — 現價 ≤ 停損價 × 103%（接近波段停損）
  NEAR_PAUSE   — 現價 ≤ 暫停線 × 103%（接近暫停線）
  NEAR_MA      — (現價 - MA20) / ATR14 < 1.0，且從上方接近月線

事件分類（差分型，需 state file）：
  WAVE_FLIP    — Wave Score 符號翻轉（正→負 或 負→正）
  WAVE_REGIME  — Wave Score 跨越 ±2 邊界（強弱分界）
  MU_FLIP      — GBM μ 由正轉負 或 由負轉正（趨勢基本面改變）

資料來源：
  輸入 1：journals/logs/{TODAY}_wave_scores.json（wave cache，wave_score_scan 已產生）
  輸入 2：trades/*.md（regex 提取目標價 / 停損價）
  輸入 3：.agents/hooks/post-daily-review/_event_state.json（前次狀態）

輸出：
  追加至 journals/logs/{TODAY}_scan.log
  更新 _event_state.json

用法：
  python scripts/event_detector.py
  python scripts/event_detector.py --dry-run
  python scripts/event_detector.py --date 2026-04-20
"""

import sys
import os
import re
import json
import glob
import argparse
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_DIR = os.path.join(BASE_DIR, 'trades')
HOOKS_DIR  = os.path.join(BASE_DIR, '.agents', 'hooks', 'post-daily-review')
LOGS_DIR   = os.path.join(BASE_DIR, 'journals', 'logs')
STATE_FILE = os.path.join(HOOKS_DIR, '_event_state.json')

TODAY = date.today().isoformat()

# 閾值常數
NEAR_TARGET_RATIO = 0.97   # 現價 >= 目標價 × 97% → 觸發 NEAR_TARGET
NEAR_STOP_RATIO   = 1.03   # 現價 <= 停損價 × 103% → 觸發 NEAR_STOP / NEAR_PAUSE
NEAR_MA_ATR_MULT  = 1.5    # (現價 - MA) / ATR < 此值 → 觸發 NEAR_MA（從上方接近）


# ── I/O 工具 ──────────────────────────────────────────────────────────────────

def load_wave_cache(today_str):
    path = os.path.join(LOGS_DIR, f'{today_str}_wave_scores.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_to_scan_log(lines, today_str):
    log_path = os.path.join(LOGS_DIR, f'{today_str}_scan.log')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('\n[事件偵測]\n')
        for line in lines:
            f.write(line + '\n')


# ── 從 trades MD 提取閾值 ─────────────────────────────────────────────────────

def extract_thresholds(md_path):
    """
    回傳 {
      'targets': [(price, stage_label), ...],  # 減持計畫觸發價
      'stop': float | None,                     # 波段停損價
      'pause': float | None,                    # 暫停線
    }
    若 MD 中無對應 section 則對應欄位為空。
    """
    try:
        with open(md_path, encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return {'targets': [], 'stop': None, 'pause': None}

    targets = []
    # 減持計畫：「站上 **X 元**」，同行通常有「第N批」標籤
    for m in re.finditer(
            r'\|\s*(第\S+批[^|]*)\|[^|]*站上\s+\*\*([\d,\.]+)\s*元\*\*', content):
        label = m.group(1).strip()
        try:
            targets.append((float(m.group(2).replace(',', '')), label))
        except ValueError:
            pass

    # 備用：沒有「第X批」欄位的簡單格式
    if not targets:
        for m in re.finditer(r'站上\s+\*\*([\d,\.]+)\s*元\*\*', content):
            try:
                targets.append((float(m.group(1).replace(',', '')), '目標'))
            except ValueError:
                pass

    # 波段停損：「波段停損」列中「跌破 **X 元**」
    stop = None
    m = re.search(
        r'波段停損[^\n]*?跌破\s+\*\*([\d,\.]+)\s*元\*\*', content)
    if m:
        try:
            stop = float(m.group(1).replace(',', ''))
        except ValueError:
            pass

    # 暫停線：「暫停線」列中「跌破 **X 元**」
    pause = None
    m = re.search(
        r'暫停線[^\n]*?跌破\s+\*\*([\d,\.]+)\s*元\*\*', content)
    if m:
        try:
            pause = float(m.group(1).replace(',', ''))
        except ValueError:
            pass

    return {'targets': targets, 'stop': stop, 'pause': pause}


def extract_name(md_path):
    try:
        with open(md_path, encoding='utf-8') as f:
            for line in f:
                m = re.search(r'# \d+_(.+?) 交易紀錄', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    # fallback：取檔名底線後的部分
    base = os.path.basename(md_path).replace('.md', '')
    return re.sub(r'^\d+_', '', base)


# ── 掃描 trades 目錄 ──────────────────────────────────────────────────────────

def find_trade_files():
    result = {}
    for fpath in glob.glob(os.path.join(TRADES_DIR, '*.md')):
        fname = os.path.basename(fpath)
        if fname.startswith('template') or fname.startswith('_'):
            continue
        m = re.match(r'^(\d+)_', fname)
        if m:
            result[m.group(1)] = fpath
    return result


# ── 事件偵測邏輯 ──────────────────────────────────────────────────────────────

def detect_events(code, r, prev, thresholds):
    """
    r       : wave cache entry（dict）
    prev    : _event_state.json 中此 code 的前次記錄（可為 None）
    thresholds: extract_thresholds() 結果

    回傳 [(event_type, message)]
    """
    events = []
    current = r['current']
    total   = r['total']
    mu      = r['mu']
    ma20    = r['ma20']
    atr14   = r.get('q_data', {}).get('atr14', 0) or 0

    # ── 閾值型 ────────────────────────────────────────────────────────────────

    for target_price, label in thresholds['targets']:
        if current >= target_price * NEAR_TARGET_RATIO:
            dist_pct = (current / target_price - 1) * 100
            events.append(('NEAR_TARGET',
                f'{label} 觸發價 {target_price:.0f} 元，現價 {current:.1f}（{dist_pct:+.1f}%）'
                f'，確認 Wave {total:+d} 是否符合減持條件'))

    if thresholds['stop']:
        if current <= thresholds['stop'] * NEAR_STOP_RATIO:
            dist_pct = (current / thresholds['stop'] - 1) * 100
            events.append(('NEAR_STOP',
                f'現價 {current:.1f} 接近波段停損 {thresholds["stop"]:.1f} 元'
                f'（距離 {dist_pct:+.1f}%）'))

    if thresholds['pause']:
        if current <= thresholds['pause'] * NEAR_STOP_RATIO:
            dist_pct = (current / thresholds['pause'] - 1) * 100
            events.append(('NEAR_PAUSE',
                f'現價 {current:.1f} 接近暫停線 {thresholds["pause"]:.1f} 元'
                f'（距離 {dist_pct:+.1f}%），底倉保護機制待確認'))

    # NEAR_MA：現價在月線上方，但 ATR 距離 < 閾值倍數
    if atr14 > 0 and current > ma20:
        gap_atr = (current - ma20) / atr14
        if gap_atr < NEAR_MA_ATR_MULT:
            events.append(('NEAR_MA',
                f'現價 {current:.1f} 距月線 {ma20:.1f} 僅 {gap_atr:.1f} ATR'
                f'（ATR={atr14:.2f}），月線支撐待確認'))

    # ── 差分型（需前次狀態）─────────────────────────────────────────────────

    if prev is None:
        return events

    last_wave = prev.get('wave_score')
    last_mu_sign = prev.get('mu_sign')

    # WAVE_FLIP：符號翻轉（跨越 0）
    if last_wave is not None:
        if (last_wave > 0 and total <= 0) or (last_wave < 0 and total >= 0):
            events.append(('WAVE_FLIP',
                f'Wave {last_wave:+d} → {total:+d}，動能方向翻轉'))

    # WAVE_REGIME：跨越 ±2 強弱邊界（但不重複回報 WAVE_FLIP）
    if last_wave is not None:
        crossed = (
            (last_wave >= 2 and total < 2) or
            (last_wave < 2 and total >= 2) or
            (last_wave <= -2 and total > -2) or
            (last_wave > -2 and total <= -2)
        )
        already_flip = any(e[0] == 'WAVE_FLIP' for e in events)
        if crossed and not already_flip:
            events.append(('WAVE_REGIME',
                f'Wave {last_wave:+d} → {total:+d}，跨越強弱邊界（±2）'))

    # MU_FLIP：GBM μ 符號翻轉
    if last_mu_sign is not None:
        curr_mu_sign = 1 if mu >= 0 else -1
        if curr_mu_sign != last_mu_sign:
            direction = 'μ 正轉負' if curr_mu_sign < 0 else 'μ 負轉正'
            events.append(('MU_FLIP',
                f'{direction}（現值 {mu*100:.1f}%），基本趨勢改變，建議執行 GBM 重算'))

    return events


# ── state 更新 ────────────────────────────────────────────────────────────────

def new_state_entry(r, today_str):
    return {
        'wave_score': r['total'],
        'mu_sign': 1 if r['mu'] >= 0 else -1,
        'mu': round(r['mu'], 4),
        'phys_s': r['phys_s'],
        'date': today_str,
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Layer 3 事件偵測')
    ap.add_argument('--dry-run', action='store_true', help='只顯示，不寫入')
    ap.add_argument('--date', default=TODAY, help='指定日期（YYYY-MM-DD）')
    args = ap.parse_args()

    today_str  = args.date
    wave_cache = load_wave_cache(today_str)

    if not wave_cache:
        print(f'⚠️  找不到 {today_str}_wave_scores.json，請先執行 wave_score_scan.py')
        sys.exit(0)   # 非致命，daily_scan.bat 繼續

    state      = load_state()
    trade_files = find_trade_files()

    all_events = []   # [(code, name, event_type, msg)]
    new_state  = dict(state)

    for code, r in wave_cache.items():
        fpath = trade_files.get(code)
        name  = extract_name(fpath) if fpath else code
        thresholds = extract_thresholds(fpath) if fpath else {
            'targets': [], 'stop': None, 'pause': None}
        prev = state.get(code)

        for etype, msg in detect_events(code, r, prev, thresholds):
            all_events.append((code, name, etype, msg))

        new_state[code] = new_state_entry(r, today_str)

    # ── 輸出 ──────────────────────────────────────────────────────────────────

    log_lines = []
    if all_events:
        print(f'[事件偵測] {today_str} — 命中 {len(all_events)} 個事件')
        for code, name, etype, msg in all_events:
            line = f'🔔 EVENT [{code} {name}] {etype}: {msg}'
            print(f'  {line}')
            log_lines.append(line)
    else:
        print(f'[事件偵測] {today_str} — 無事件')

    if not args.dry_run:
        if log_lines:
            append_to_scan_log(log_lines, today_str)
            print(f'  → 已寫入 {today_str}_scan.log')
        save_state(new_state)
    else:
        print('  [dry-run，未寫入]')


if __name__ == '__main__':
    main()
