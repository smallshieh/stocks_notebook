"""
watchlist_update_apply.py — 套用 _watchlist_update_data.json 到 watchlist/*.md
"""
import sys
import os
import re
import json

sys.stdout.reconfigure(encoding='utf-8')

DATA = 's:/股票筆記/scripts/_watchlist_update_data.json'
WATCHLIST = 's:/股票筆記/watchlist'

def fmt_price(v):
    if v is None:
        return '—'
    if v >= 100:
        return f'{v:.1f}'
    return f'{v:.2f}'

def fmt_pct(p):
    return f'{p*100:.1f}%'

def build_gbm_block(r):
    d = r['last_date']
    code = r['code']
    c = r['current']
    mu = r['mu']
    sigma = r['sigma']
    ss = r['sigma_src']
    p20, p60, p120 = r['p20'], r['p60'], r['p120']

    block = f"""## GBM 幾何布朗運動機率預測（{d} 更新）

```text
=== {code} GBM ===
現價            ：{fmt_price(c)} 元
趨勢漂移率 μ      ：{mu:+.1f}% (年化)
年化波動率 σ      ：{sigma:.1f}%（{ss}）

  20d: 期望 {fmt_price(p20['expected'])} | +1σ {fmt_price(p20['+1sigma_price'])}({fmt_pct(p20['+1sigma_p'])}) | +1.5σ {fmt_price(p20['+1.5sigma_price'])}({fmt_pct(p20['+1.5sigma_p'])}) | -1σ {fmt_price(p20['-1sigma_price'])}({fmt_pct(p20['-1sigma_p'])}) | -1.5σ {fmt_price(p20['-1.5sigma_price'])}({fmt_pct(p20['-1.5sigma_p'])})
  60d: 期望 {fmt_price(p60['expected'])} | +1σ {fmt_price(p60['+1sigma_price'])}({fmt_pct(p60['+1sigma_p'])}) | +1.5σ {fmt_price(p60['+1.5sigma_price'])}({fmt_pct(p60['+1.5sigma_p'])}) | -1σ {fmt_price(p60['-1sigma_price'])}({fmt_pct(p60['-1sigma_p'])})
 120d: 期望 {fmt_price(p120['expected'])} | +1σ {fmt_price(p120['+1sigma_price'])}({fmt_pct(p120['+1sigma_p'])}) | +1.5σ {fmt_price(p120['+1.5sigma_price'])}({fmt_pct(p120['+1.5sigma_p'])}) | -1σ {fmt_price(p120['-1sigma_price'])}({fmt_pct(p120['-1sigma_p'])})
```

> 機率為 Monte Carlo 路徑觸及機率（30,000 sims），代表期間內「至少摸到」該價位，非終點機率。
"""
    return block

def update_file(path, r):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    orig = text
    d = r['last_date']
    c = r['current']
    ma20 = r.get('ma20')

    # 1) 替換 目前價格（list 行）
    pat_price_list = re.compile(r'\*\*目前價格\*\*\s*[:：][^\n]*')
    text = pat_price_list.sub(f'**目前價格**: {fmt_price(c)} 元（{d} Yahoo 收盤）', text, count=1)

    # 替換 table 的「| 現價 | ... |」
    pat_price_tbl = re.compile(r'(\|\s*現價\s*\|\s*)[^\|\n]+(\|)')
    text = pat_price_tbl.sub(rf'\g<1>{fmt_price(c)} 元 \g<2>', text, count=1)

    # 2) 替換 月線 / 20MA
    if ma20 is not None:
        pat_ma_list = re.compile(r'\*\*月線\s*\(?20MA\)?\*\*\s*[:：][^\n]*')
        text = pat_ma_list.sub(f'**月線 (20MA)**: {fmt_price(ma20)} 元（{d} Yahoo）', text, count=1)
        pat_ma_tbl1 = re.compile(r'(\|\s*20MA（月線）\s*\|\s*)[^\|\n]+(\|)')
        text = pat_ma_tbl1.sub(rf'\g<1>{fmt_price(ma20)} 元（{d}）\g<2>', text, count=1)
        pat_ma_tbl2 = re.compile(r'(\|\s*月線\s*\(20MA\)\s*位置\s*\|\s*)[^\|\n]+(\|)')
        text = pat_ma_tbl2.sub(rf'\g<1>{fmt_price(ma20)} 元 \g<2>', text, count=1)

    # 3) 替換/追加 GBM 區塊
    gbm_block = build_gbm_block(r)
    pat_gbm = re.compile(r'## GBM 幾何布朗運動機率預測[^\n]*\n(?:.*?)(?=\n## |\Z)', re.DOTALL)
    if pat_gbm.search(text):
        text = pat_gbm.sub(gbm_block.rstrip() + '\n', text, count=1)
    else:
        text = text.rstrip() + '\n\n---\n\n' + gbm_block

    if text != orig:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return True
    return False

def main():
    with open(DATA, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changed = 0
    for r in data:
        if 'error' in r:
            print(f'⚠️  跳過 {r["code"]} {r["name"]}: {r["error"]}')
            continue
        path = os.path.join(WATCHLIST, r['file'])
        if not os.path.exists(path):
            print(f'❌ 找不到 {path}')
            continue
        ok = update_file(path, r)
        mark = '✅ 已更新' if ok else '🟡 無變更'
        p20e = r['p20']['expected']
        up1p = r['p20']['+1sigma_p']
        print(f'{mark} {r["file"]} | 現價 {r["current"]} → 20d期望 {p20e:.1f} (+1σ P={up1p*100:.0f}%)')
        if ok:
            changed += 1
    print(f'\n總計 {changed} 檔已更新')

if __name__ == '__main__':
    main()
