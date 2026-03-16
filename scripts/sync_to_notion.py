#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_to_notion.py — 將 MD 檔單向同步到 Notion 子頁面

改善：
  - Hash 快取：內容未變更則跳過（.notion_sync_cache.json）
  - 並行刪除：ThreadPoolExecutor，加速 clear_page
  - 多檔支援：一次呼叫可傳多個檔案
  - --all    ：掃描 trades/ journals/ strategies/ 全部 MD 並同步

用法：
  python scripts/sync_to_notion.py                              # 預設同步戰術指南
  python scripts/sync_to_notion.py journals/戰術指南.md
  python scripts/sync_to_notion.py trades/2330_台積電.md trades/2317_鴻海.md
  python scripts/sync_to_notion.py --all                        # 同步所有 MD（跳過未變更）
  python scripts/sync_to_notion.py --all --force                # 強制重新同步全部
  python scripts/sync_to_notion.py journals/戰術指南.md --force  # 強制重新同步單檔

設定方式（擇一）：
  1. 環境變數：set NOTION_TOKEN=... && set NOTION_PARENT_PAGE_ID=...
  2. 建立 scripts/notion_creds.py（已 gitignore），內容：
       NOTION_TOKEN          = "secret_xxx..."
       NOTION_PARENT_PAGE_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
"""

import re
import sys
import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8')

# ── 讀取憑證 ──────────────────────────────────────────────────────────────────
NOTION_TOKEN          = os.environ.get("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "")

_CREDS = Path(__file__).parent / "notion_creds.py"
if _CREDS.exists() and (not NOTION_TOKEN or not NOTION_PARENT_PAGE_ID):
    import importlib.util
    _spec = importlib.util.spec_from_file_location("notion_creds", _CREDS)
    _mod  = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    NOTION_TOKEN          = NOTION_TOKEN          or getattr(_mod, "NOTION_TOKEN",          "")
    NOTION_PARENT_PAGE_ID = (NOTION_PARENT_PAGE_ID
                             or getattr(_mod, "NOTION_PARENT_PAGE_ID", "")
                             or getattr(_mod, "NOTION_PAGE_ID",        ""))

_BASE       = Path(__file__).parent.parent
_DEFAULT    = _BASE / "journals" / "戰術指南.md"
_CACHE_FILE = Path(__file__).parent / ".notion_sync_cache.json"

# --all 掃描的目錄
_SCAN_DIRS = ["trades", "journals", "strategies", "watchlist"]


# ─────────────────────────────────────────────────────────────────────────────
# Hash 快取（跳過未變更檔案）
# ─────────────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


def _md5(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _cache_key(md_path: Path) -> str:
    """使用相對於專案根目錄的路徑作為 cache key。"""
    try:
        return str(md_path.relative_to(_BASE))
    except ValueError:
        return str(md_path)


def is_unchanged(md_path: Path, content: str, cache: dict) -> bool:
    key = _cache_key(md_path)
    return cache.get(key, {}).get("md5") == _md5(content)


def update_cache(md_path: Path, content: str, page_id: str, cache: dict):
    key = _cache_key(md_path)
    cache[key] = {
        "md5": _md5(content),
        "page_id": page_id,
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 子頁面標題推斷
# ─────────────────────────────────────────────────────────────────────────────

def get_page_title(md_path: Path) -> str:
    return md_path.stem.replace('_', ' ', 1)


# ─────────────────────────────────────────────────────────────────────────────
# Notion block 建構函式
# ─────────────────────────────────────────────────────────────────────────────

def _rich(text: str) -> list:
    parts = []
    pat = re.compile(r'\*\*(.*?)\*\*')
    last = 0
    for m in pat.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        parts.append({
            "type": "text",
            "text": {"content": m.group(1)},
            "annotations": {"bold": True},
        })
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    return parts or [{"type": "text", "text": {"content": text}}]


def _heading(level: int, text: str) -> dict:
    k = f"heading_{level}"
    return {"object": "block", "type": k, k: {"rich_text": _rich(text.strip())}}


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich(text)}}


def _quote(text: str) -> dict:
    return {"object": "block", "type": "quote",
            "quote": {"rich_text": _rich(text)}}


def _code(text: str) -> dict:
    MAX = 1990
    if len(text) > MAX:
        text = text[:MAX] + "\n…（截斷）"
    return {"object": "block", "type": "code",
            "code": {"rich_text": [{"type": "text", "text": {"content": text}}],
                     "language": "plain text"}}


def _table(rows: list) -> dict:
    parsed = []
    for row in rows:
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        parsed.append(cells)
    width = max(len(c) for c in parsed)
    table_rows = []
    for cells in parsed:
        padded = cells + [''] * (width - len(cells))
        table_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [[{"type": "text", "text": {"content": c}}] for c in padded]
            },
        })
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Markdown 解析器
# ─────────────────────────────────────────────────────────────────────────────

_SEP_RE   = re.compile(r'^-{3,}\s*$')
_TABLE_RE = re.compile(r'^\s*\|[-:\s|]+\|\s*$')


def parse_md(content: str) -> list:
    blocks = []
    lines  = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            blocks.append(_code('\n'.join(code_lines)))

        elif line.startswith('### '):
            blocks.append(_heading(3, line[4:]))
        elif line.startswith('## '):
            blocks.append(_heading(2, line[3:]))
        elif line.startswith('# '):
            blocks.append(_heading(1, line[2:]))

        elif _SEP_RE.match(line):
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        elif line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                if not _TABLE_RE.match(lines[i]):
                    table_lines.append(lines[i])
                i += 1
            if table_lines:
                blocks.append(_table(table_lines))
            continue

        elif line.startswith('> '):
            blocks.append(_quote(line[2:]))

        elif line.startswith('- ') or line.startswith('  - '):
            text = line.lstrip('- ')
            blocks.append(_bullet(text))

        elif line.strip() == '':
            pass

        else:
            blocks.append(_paragraph(line))

        i += 1

    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# Notion API 操作
# ─────────────────────────────────────────────────────────────────────────────

def find_child_page(client, parent_id: str, title: str) -> Optional[str]:
    has_more, cursor = True, None
    while has_more:
        kw = {"block_id": parent_id}
        if cursor:
            kw["start_cursor"] = cursor
        result = client.blocks.children.list(**kw)
        for block in result["results"]:
            if block["type"] == "child_page" and block["child_page"]["title"] == title:
                return block["id"]
        has_more = result.get("has_more", False)
        cursor   = result.get("next_cursor")
    return None


def create_child_page(client, parent_id: str, title: str) -> str:
    page = client.pages.create(
        parent={"type": "page_id", "page_id": parent_id},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        }
    )
    return page["id"]


def find_or_create_child_page(client, parent_id: str, title: str) -> Tuple[str, bool]:
    page_id = find_child_page(client, parent_id, title)
    if page_id:
        return page_id, False
    page_id = create_child_page(client, parent_id, title)
    return page_id, True


def _delete_block_with_retry(client, bid: str, max_retries: int = 3):
    """刪除單一 block，遇 429 自動退讓重試。"""
    for attempt in range(max_retries):
        try:
            client.blocks.delete(block_id=bid)
            return True
        except Exception as e:
            if "rate_limited" in str(e).lower() or "429" in str(e):
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
            else:
                return False  # 非 rate limit 錯誤（如 archived），直接跳過
    return False


def clear_page(client, page_id: str):
    """收集所有 block ID，然後以並行方式刪除（3 workers，尊重 rate limit）。"""
    block_ids = []
    has_more, cursor = True, None
    while has_more:
        kw = {"block_id": page_id}
        if cursor:
            kw["start_cursor"] = cursor
        result  = client.blocks.children.list(**kw)
        block_ids.extend(b["id"] for b in result["results"])
        has_more = result.get("has_more", False)
        cursor   = result.get("next_cursor")

    if not block_ids:
        print("  （頁面已空）")
        return

    deleted = skipped = 0
    # Notion 3 req/s 限制，用 3 workers 大致貼近上限
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_delete_block_with_retry, client, bid): bid
                   for bid in block_ids}
        for f in as_completed(futures):
            if f.result():
                deleted += 1
            else:
                skipped += 1
    msg = f"  已清除 {deleted} 個舊 blocks"
    if skipped:
        msg += f"（跳過 {skipped} 個）"
    print(msg)


def append_blocks(client, page_id: str, blocks: list):
    """分批（每批 100 個）append blocks 到頁面。"""
    total = 0
    for start in range(0, len(blocks), 100):
        batch = blocks[start:start + 100]
        client.blocks.children.append(block_id=page_id, children=batch)
        total += len(batch)
        print(f"  已上傳 {total}/{len(blocks)} blocks")


# ─────────────────────────────────────────────────────────────────────────────
# 單檔同步
# ─────────────────────────────────────────────────────────────────────────────

def sync_file(client, md_path: Path, cache: dict, force: bool = False) -> bool:
    """同步單一 MD 檔到 Notion。回傳 True = 有實際同步，False = 跳過。"""
    content = md_path.read_text(encoding='utf-8')

    if not force and is_unchanged(md_path, content, cache):
        print(f"  ⏩ 跳過（內容未變更）：{md_path.name}")
        return False

    title = get_page_title(md_path)
    print(f"\n{'='*50}")
    print(f"📄 {md_path.name}  →  「{title}」")

    blocks = parse_md(content)
    print(f"  解析完成：{len(blocks)} 個 blocks")

    page_id, is_new = find_or_create_child_page(client, NOTION_PARENT_PAGE_ID, title)
    if is_new:
        print(f"  建立新子頁面：{page_id}")
    else:
        print(f"  找到既有子頁面，清除舊內容…")
        clear_page(client, page_id)

    append_blocks(client, page_id, blocks)
    update_cache(md_path, content, page_id, cache)
    print(f"  ✅ 完成！{len(blocks)} blocks")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def collect_all_md_files() -> list:
    """收集 _SCAN_DIRS 下所有 .md 檔（排除 template.md）。"""
    files = []
    for d in _SCAN_DIRS:
        scan_dir = _BASE / d
        if scan_dir.exists():
            for p in sorted(scan_dir.rglob("*.md")):
                if p.name != "template.md":
                    files.append(p)
    # 根目錄的獨立 MD（戰術指南等）
    for p in sorted(_BASE.glob("*.md")):
        files.append(p)
    return files


def main():
    if not NOTION_TOKEN or not NOTION_PARENT_PAGE_ID:
        print("❌ 缺少憑證！請設定 NOTION_TOKEN / NOTION_PARENT_PAGE_ID")
        sys.exit(1)

    args = sys.argv[1:]
    force   = "--force" in args
    all_mode = "--all" in args
    args = [a for a in args if a not in ("--force", "--all")]

    try:
        from notion_client import Client
    except ImportError:
        print("❌ 未安裝 notion-client，請執行：pip install notion-client")
        sys.exit(1)

    client = Client(auth=NOTION_TOKEN)
    cache  = _load_cache()

    if all_mode:
        md_files = collect_all_md_files()
        print(f"--all 模式：共找到 {len(md_files)} 個 MD 檔")
    elif args:
        md_files = []
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = _BASE / p
            if not p.exists():
                print(f"⚠️  找不到檔案：{p}，略過")
            else:
                md_files.append(p)
    else:
        md_files = [_DEFAULT]
        if not _DEFAULT.exists():
            print(f"❌ 找不到預設檔案：{_DEFAULT}")
            sys.exit(1)

    synced = skipped = 0
    for md_path in md_files:
        did_sync = sync_file(client, md_path, cache, force=force)
        if did_sync:
            synced += 1
        else:
            skipped += 1
        _save_cache(cache)  # 每同步一檔就存一次，避免中途失敗損失進度

    print(f"\n{'='*50}")
    print(f"同步完成：{synced} 個檔案已更新，{skipped} 個跳過（未變更）")


if __name__ == "__main__":
    main()
