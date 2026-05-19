"""汇总所有因子分析结果到 factor_summary.csv。"""
import pandas as pd
import json, os, re, glob

OUT_DIR = 'output'
DATA_DIR = 'output/data_processed'


def load_config():
    with open('industry/run_config.json') as f:
        return json.load(f)


def get_periods(cfg):
    """返回 [(周期名, 分析目录), ...]"""
    periods = [('full', f'{OUT_DIR}/factor_analysis')]
    sp = cfg.get('sub_period', {})
    if 'from_file' in sp:
        ext = json.load(open(sp['from_file']))
        names = sp.get('groups', list(ext.keys()))
        for name in names:
            suffix = ext[name]['suffix']
            periods.append((suffix, f'{OUT_DIR}/factor_analysis_{suffix}'))
    return periods


def get_factors(cfg):
    """返回所有配置的因子（行业 + 月度），含 meta。"""
    factors = []
    for key in ('industry_factors', 'monthly_factors'):
        src = cfg.get(key, {})
        for col, meta in src.items():
            factors.append((col, meta['label'], meta['cat'], key))
    return factors


def read_ic(factor_dir, col):
    """解析 IC 文本，返回各 horizon 的 ic_mean 和 icir。"""
    path = f'{factor_dir}/ic/{col}_ic.txt'
    if not os.path.exists(path):
        return {}
    text = open(path).read()
    result = {}
    # 段落：T+1（所有因子都有）
    m = re.search(r'IC 均值:\s+([\d.-]+)', text)
    if m:
        result['ic_mean_T1'] = float(m.group(1))
    m = re.search(r'ICIR:\s+([\d.-]+)', text)
    if m:
        result['icir_T1'] = float(m.group(1))
    # 表格：T+5 / T+10 / T+22（只有日度因子有）
    for h in [5, 10, 22]:
        m = re.search(rf'T\+{h}\s+([\d.-]+)\s+[\d.-]+\s+([\d.-]+)', text)
        if m:
            result[f'ic_mean_T{h}'] = float(m.group(1))
            result[f'icir_T{h}'] = float(m.group(2))
    return result


def read_rr(factor_dir, col):
    """解析 RR 文本，返回胜率和尾部赔率。"""
    path = f'{factor_dir}/rr/{col}_rr.txt'
    if not os.path.exists(path):
        return {}
    text = open(path).read()
    result = {}
    m = re.search(r'胜率\s+([\d.]+)\s+([\d.]+)', text)
    if m:
        result['long_win'] = float(m.group(1))
        result['short_win'] = float(m.group(2))
    m = re.search(r'尾部赔率\s+([\d.]+)\s+([\d.]+)', text)
    if m:
        result['long_odds'] = float(m.group(1))
        result['short_odds'] = float(m.group(2))
    return result


def read_sig(factor_dir, col):
    """解析 SIG 文本，返回峰度和 ACF。"""
    path = f'{factor_dir}/sig/{col}_sig.txt'
    if not os.path.exists(path):
        return {}
    text = open(path).read()
    result = {}
    m = re.search(r'峰度 \(超额\):\s+([\d.-]+)', text)
    if m:
        result['kurtosis'] = float(m.group(1))
    m = re.search(r'ACF\(1\) 均值:\s+([\d.-]+)', text)
    if m:
        result['acf1_mean'] = float(m.group(1))
    m = re.search(r'标准差:\s+([\d.-]+)', text)
    if m:
        result['acf1_std'] = float(m.group(1))
    return result


def read_ret(factor_dir, col):
    """解析 ret 文本，返回十分组收益。"""
    path = f'{factor_dir}/ret/{col}_ret.txt'
    if not os.path.exists(path):
        return {}
    result = {}
    for line in open(path):
        k, v = line.strip().split('=')
        result[k] = float(v)
    return result


def _parse_label(factor_dir, col):
    """从 IC/RR/SIG 文本中解析因子中文名。"""
    for txt in (f'{factor_dir}/ic/{col}_ic.txt',
                f'{factor_dir}/rr/{col}_rr.txt',
                f'{factor_dir}/sig/{col}_sig.txt'):
        if os.path.exists(txt):
            m = re.search(rf'{re.escape(col)}\s*\((.+?)\)', open(txt).read())
            if m:
                return m.group(1)
    return col


def scan_factors():
    """扫描分析目录，所有有分析结果的因子全纳入。"""
    factors = set()
    for ic_file in glob.glob(f'{OUT_DIR}/factor_analysis/*/*/ic/*_ic.txt'):
        col = os.path.basename(ic_file).replace('_ic.txt', '')
        cat = ic_file.split('/')[-4]
        factor_dir = f'{OUT_DIR}/factor_analysis/{cat}/{col}'
        label = _parse_label(factor_dir, col)
        factors.add((col, label, cat))
    return list(factors)


def main():
    cfg = load_config()
    factors = scan_factors()
    periods = get_periods(cfg)

    rows = []
    for col, label, cat in factors:
        for period_name, base_path in periods:
            factor_dir = f'{base_path}/{cat}/{col}'
            row = {'factor': col, 'label': label, 'cat': cat, 'period': period_name}
            row.update(read_ic(factor_dir, col))
            row.update(read_rr(factor_dir, col))
            row.update(read_sig(factor_dir, col))
            row.update(read_ret(factor_dir, col))
            # 跳过全空行（如无数据的 consolidate）
            if len(row) <= 4:
                continue
            rows.append(row)

    if not rows:
        print('无汇总数据')
        return

    df = pd.DataFrame(rows)
    # 月度因子排在最后
    df['_sort'] = df['cat'].map({'monthly': 1}).fillna(0)
    df = df.sort_values(['_sort', 'cat', 'factor', 'period']).drop(columns=['_sort'])
    # 胜率转百分数，其余数值保留四位小数
    pct_cols = {'long_win', 'short_win'}
    for c in df.columns:
        if c in ('factor', 'label', 'cat', 'period'):
            continue
        if c in pct_cols:
            df[c] = df[c] * 100
        df[c] = df[c].round(4)
    os.makedirs(f'{OUT_DIR}/result', exist_ok=True)
    out_path = f'{OUT_DIR}/result/factor_summary.csv'
    df.to_csv(out_path, index=False, float_format='%.4f', encoding='utf-8-sig')
    print(f'汇总表保存: {len(df)} 行, {len(df.columns)} 列 → {out_path}')


if __name__ == '__main__':
    main()
