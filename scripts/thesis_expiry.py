"""
thesis_expiry.py — 前瞻觀點與催化劑到期提醒
==============================================
掃描兩個來源，找出即將到期或已過期的項目：
  1. strategies/thesis_tracking.md — Active 區的「驗證時點」
  2. trades/*.md — 催化劑表中帶有未來日期的項目

用法：
  # 完整報告
  python scripts/thesis_expiry.py

  # 靜默模式（供 hook 呼叫，只輸出摘要行）
  python scripts/thesis_expiry.py --quiet

  # 自訂提醒天數
  python scripts/thesis_expiry.py --warn-days 14 --preview-days 60
"""

import sys
import os
import re
import argparse
from datetime import datetime, date

sys.stdout.reconfigure(encoding='utf-8')

PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
THESIS_FILE = os.path.join(PROJ_ROOT, 'strategies', 'thesis_tracking.md')
TRADES_DIR = os.path.join(PROJ_ROOT, 'trades')

TODAY = date.today()


# ── 解析 thesis_tracking.md ─────────────────────────────────────────────────

def parse_thesis_active(filepath: str) -> list[dict]:
    """解析 Active 區的 thesis entries，提取 ID、標題、驗證時點、狀態"""
    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 切出 Active 區塊（從 ## Active 到下一個 ## 或檔尾）
    active_match = re.search(
        r'^## Active.*?\n(.*?)(?=^## |\Z)',
        content, re.MULTILINE | re.DOTALL
    )
    if not active_match:
        return []

    active_text = active_match.group(1)
    entries = []

    # 找每個 ### T-NNN 開頭的 entry
    entry_blocks = re.split(r'(?=^### T-\d+)', active_text, flags=re.MULTILINE)
    for block in entry_blocks:
        if not block.strip():
            continue

        # 標題行：### T-001 [2026-04-15] 尼可拉斯楊｜...
        title_match = re.match(
            r'### (T-\d+)\s+\[(\d{4}-\d{2}-\d{2})\]\s+(.*)',
            block.strip()
        )
        if not title_match:
            continue

        tid = title_match.group(1)
        entry_date = title_match.group(2)
        title = title_match.group(3).strip()

        # 驗證時點
        verify_match = re.search(
            r'\*\*驗證時點\*\*[：:]\s*(\d{4}-\d{2}-\d{2})',
            block
        )
        verify_date = verify_match.group(1) if verify_match else None

        # 狀態
        status_match = re.search(
            r'\*\*狀態\*\*[：:]\s*(.*)',
            block
        )
        status = status_match.group(1).strip() if status_match else '未知'

        # 論點摘要（取第一行）
        thesis_match = re.search(
            r'\*\*論點\*\*[：:]\s*(.*)',
            block
        )
        thesis = thesis_match.group(1).strip()[:60] if thesis_match else ''

        entries.append({
            'source': 'thesis_tracking',
            'id': tid,
            'title': title,
            'entry_date': entry_date,
            'verify_date': verify_date,
            'status': status,
            'summary': thesis,
        })

    return entries


# ── 解析 trades 催化劑表 ────────────────────────────────────────────────────

def parse_trade_catalysts(trades_dir: str) -> list[dict]:
    """掃描 trades/*.md 的催化劑表，找出日期在未來的項目"""
    if not os.path.isdir(trades_dir):
        return []

    entries = []

    for fname in os.listdir(trades_dir):
        if not fname.endswith('.md') or fname == 'template.md':
            continue

        filepath = os.path.join(trades_dir, fname)

        # 從檔名解析代號和名稱
        name_match = re.match(r'(\d+)_(.+)\.md', fname)
        if not name_match:
            continue
        code = name_match.group(1)
        name = name_match.group(2)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 找催化劑表區塊
        cat_match = re.search(
            r'^## 重要事件與催化劑.*?\n(.*?)(?=^## |\Z)',
            content, re.MULTILINE | re.DOTALL
        )
        if not cat_match:
            continue

        cat_text = cat_match.group(1)

        # 解析表格行：| 日期 | 事件 | 來源 | 影響評估 | 行動 |
        for line in cat_text.split('\n'):
            line = line.strip()
            if not line.startswith('|'):
                continue

            cols = [c.strip() for c in line.split('|')]
            # 至少要有 日期, 事件, 來源, 影響評估, 行動
            if len(cols) < 6:
                continue

            date_str = cols[1]
            event = cols[2]
            source = cols[3]
            impact = cols[4]
            action = cols[5]

            # 解析日期
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', date_str)
            if not date_match:
                continue

            try:
                event_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
            except ValueError:
                continue

            # 只收錄未來日期的項目
            if event_date <= TODAY:
                continue

            # 清理 markdown bold
            event_clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', event)

            entries.append({
                'source': f'trades/{code}_{name}',
                'id': f'{code}-cat',
                'title': f'[{code}] {event_clean[:50]}',
                'entry_date': date_match.group(1),
                'verify_date': date_match.group(1),
                'status': impact,
                'summary': f'行動: {action}',
            })

    return entries


# ── 分類與排序 ──────────────────────────────────────────────────────────────

def classify_entries(entries: list[dict], warn_days: int, preview_days: int) -> dict:
    """將 entries 分為 overdue / urgent / upcoming 三類"""
    overdue = []   # 已過期未驗
    urgent = []    # warn_days 內到期
    upcoming = []  # preview_days 內到期

    for e in entries:
        if not e['verify_date']:
            continue

        try:
            vdate = datetime.strptime(e['verify_date'], '%Y-%m-%d').date()
        except ValueError:
            continue

        days_left = (vdate - TODAY).days

        e['days_left'] = days_left
        e['verify_date_obj'] = vdate

        if days_left < 0:
            overdue.append(e)
        elif days_left <= warn_days:
            urgent.append(e)
        elif days_left <= preview_days:
            upcoming.append(e)

    # 按到期日排序
    overdue.sort(key=lambda x: x['days_left'])
    urgent.sort(key=lambda x: x['days_left'])
    upcoming.sort(key=lambda x: x['days_left'])

    return {'overdue': overdue, 'urgent': urgent, 'upcoming': upcoming}


# ── 輸出格式 ────────────────────────────────────────────────────────────────

def format_entry_line(e: dict) -> str:
    """格式化單一 entry 為一行摘要"""
    days = e['days_left']
    if days < 0:
        time_str = f'已過期 {-days} 天'
        icon = '🚨'
    elif days == 0:
        time_str = '今天到期'
        icon = '🚨'
    elif days <= 7:
        time_str = f'剩 {days} 天'
        icon = '⏰'
    else:
        time_str = f'剩 {days} 天'
        icon = '📅'

    return f'{icon} {e["id"]} {e["title"]}：{time_str} ({e["verify_date"]})'


def format_quiet(classified: dict) -> str:
    """靜默模式：一行摘要"""
    total = sum(len(v) for v in classified.values())
    if total == 0:
        return '無到期項目'

    parts = []
    if classified['overdue']:
        parts.append(f'🚨過期{len(classified["overdue"])}')
    if classified['urgent']:
        parts.append(f'⏰即將{len(classified["urgent"])}')
    if classified['upcoming']:
        parts.append(f'📅預覽{len(classified["upcoming"])}')

    detail_entries = classified['overdue'] + classified['urgent']
    details = []
    for e in detail_entries[:3]:  # 最多列 3 筆細節
        days = e['days_left']
        if days < 0:
            details.append(f'{e["id"]}({-days}天前到期)')
        else:
            details.append(f'{e["id"]}(剩{days}天)')

    summary = ', '.join(parts)
    if details:
        summary += ' | ' + ', '.join(details)

    return summary


def format_full(classified: dict) -> str:
    """完整報告"""
    lines = [f'=== 前瞻觀點到期追蹤 ({TODAY}) ===', '']

    if not any(classified.values()):
        lines.append('所有觀點均不在提醒範圍內（無過期、無即將到期）。')
        return '\n'.join(lines)

    if classified['overdue']:
        lines.append(f'🚨 已過期未驗（{len(classified["overdue"])} 筆）：')
        for e in classified['overdue']:
            lines.append(f'  {format_entry_line(e)}')
            lines.append(f'    → {e["summary"]}')
        lines.append('')

    if classified['urgent']:
        lines.append(f'⏰ 即將到期（{len(classified["urgent"])} 筆）：')
        for e in classified['urgent']:
            lines.append(f'  {format_entry_line(e)}')
            lines.append(f'    → {e["summary"]}')
        lines.append('')

    if classified['upcoming']:
        lines.append(f'📅 未來預覽（{len(classified["upcoming"])} 筆）：')
        for e in classified['upcoming']:
            lines.append(f'  {format_entry_line(e)}')
        lines.append('')

    return '\n'.join(lines)


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='前瞻觀點與催化劑到期提醒')
    parser.add_argument('--quiet', action='store_true',
                        help='靜默模式，只輸出摘要行')
    parser.add_argument('--warn-days', type=int, default=7,
                        help='幾天內到期視為「即將到期」（預設 7）')
    parser.add_argument('--preview-days', type=int, default=30,
                        help='幾天內到期顯示預覽（預設 30）')
    args = parser.parse_args()

    # 收集所有 entries
    entries = []
    entries.extend(parse_thesis_active(THESIS_FILE))
    entries.extend(parse_trade_catalysts(TRADES_DIR))

    # 分類
    classified = classify_entries(entries, args.warn_days, args.preview_days)

    # 輸出
    if args.quiet:
        print(format_quiet(classified))
    else:
        print(format_full(classified))


if __name__ == '__main__':
    main()
