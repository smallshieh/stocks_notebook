import os
import re

drift_data = {
    '6239': ('+88.3%', '🚀 長線趨勢股'),
    '2330': ('+84.8%', '🚀 長線趨勢股'),
    '6488': ('+53.0%', '🚀 長線趨勢股'),
    '1503': ('+48.9%', '🚀 長線趨勢股'),
    '3231': ('+47.4%', '🚀 長線趨勢股'),
    '2317': ('+47.3%', '🚀 長線趨勢股'),
    '2454': ('+46.2%', '🚀 長線趨勢股'),
    '2382': ('+31.7%', '📈 穩健走升股'),
    '5483': ('+16.7%', '📈 穩健走升股'),
    '2357': ('+9.8%', '⚖️ 區間盤整股'),
    '2886': ('+7.2%', '⚖️ 區間盤整股'),
    '1210': ('+1.5%', '⚖️ 區間盤整股'),
    '2379': ('-0.9%', '⚖️ 區間盤整股'),
    '2002': ('-13.3%', '⚖️ 區間盤整股'),
    '4938': ('-15.4%', '⚖️ 區間盤整股'),
    '3034': ('-20.0%', '⚖️ 區間盤整股'),
    '8069': ('-34.4%', '⚖️ 區間盤整股')
}

trades_dir = r's:\股票筆記\trades'

def update_file(filename):
    # Extract code from filename e.g. '2330_台積電.md'
    match = re.match(r'^(\d+)_', filename)
    if not match:
        return
    code = match.group(1)
    
    if code not in drift_data:
        return
    
    mu, strategy = drift_data[code]
    info_line = f"- **量化屬性**: {strategy} (1y GBM 漂移率 $\mu$ = {mu})\n"
    
    filepath = os.path.join(trades_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Don't add if already exists
    if any("量化屬性" in line for line in lines):
        # Update existing line
        new_lines = []
        for line in lines:
            if "量化屬性" in line:
                new_lines.append(info_line)
            else:
                new_lines.append(line)
        lines = new_lines
    else:
        # Insert after ## 基本資訊 header
        found_header = False
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if line.startswith('## 基本資訊'):
                new_lines.append(info_line)
                found_header = True
        
        if not found_header:
            return
        lines = new_lines

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"Updated {filename}: {mu} {strategy}")

for filename in os.listdir(trades_dir):
    if filename.endswith('.md') and filename != 'template.md':
        update_file(filename)
