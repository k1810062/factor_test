"""汇总所有因子分析结果到 factor_summary.csv。"""
import pandas as pd
import json, os, re, glob

def _output_dir():
    """从配置文件读输出目录，没有则默认 'output'。"""
    try:
        cfg = load_config()
        analysis_dir = cfg.get('analysis_dir', 'output/factor_analysis')
        return os.path.dirname(analysis_dir)
    except Exception:
        return 'output'


def load_config():
    path = 'config/config.json'
    if not os.path.exists(path):
        path = 'industry/run_config.json'
    with open(path) as f:
        return json.load(f)


def get_periods(cfg):
    """返回 [(周期名, 分析目录), ...]"""
    periods = [('full', f'{_output_dir()}/factor_analysis')]
    sp = cfg.get('sub_period', {})
    if 'from_file' in sp:
        ext = json.load(open(sp['from_file']))
        names = sp.get('groups', list(ext.keys()))
        for name in names:
            suffix = ext[name]['suffix']
            periods.append((suffix, f'{_output_dir()}/factor_analysis_{suffix}'))
    return periods


def get_factors(cfg):
    """返回所有配置的因子（行业 + 月度），含 meta。兼容新旧格式。"""
    factors = []
    # 新格式: industry/monthly  旧格式: industry_factors/monthly_factors
    for new_key, old_key in (('industry', 'industry_factors'), ('monthly', 'monthly_factors')):
        src = cfg.get(new_key) or cfg.get(old_key, {})
        for col, meta in src.items():
            factors.append((col, meta['label'], meta['cat'], old_key))
    return factors


def read_ic(factor_dir, col):
    """读 IC JSON，返回各 horizon 的 ic_mean 和 icir。"""
    path = f'{factor_dir}/ic/{col}_ic.json'
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    result = {'ic_T1': data['ic_mean'], 'icir_T1': data['icir']}
    for h in data.get('horizons', []):
        result[f'ic_T{h["h"]}'] = h['ic_mean']
        result[f'icir_T{h["h"]}'] = h['icir']
    return result


def read_rr(factor_dir, col):
    """读 RR JSON，返回胜率和尾部赔率。"""
    path = f'{factor_dir}/rr/{col}_rr.json'
    if not os.path.exists(path):
        return {}
    return json.load(open(path))


def read_sig(factor_dir, col):
    """读 SIG JSON，返回峰度和 ACF。"""
    path = f'{factor_dir}/sig/{col}_sig.json'
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    result = {
        'kurtosis': data.get('excess_kurt', data.get('kurtosis', 0)),
        'acf1_mean': data.get('acf1_mean', 0),
        'acf1_std': data.get('acf1_std', 0),
    }
    return result


def read_ret(factor_dir, col):
    """读 RET JSON，返回十分组收益。"""
    path = f'{factor_dir}/ret/{col}_ret.json'
    if not os.path.exists(path):
        return {}
    return json.load(open(path))


def _parse_label(factor_dir, col):
    """从 IC JSON 中解析因子中文名。"""
    for p in (f'{factor_dir}/ic/{col}_ic.json',
              f'{factor_dir}/rr/{col}_rr.json',
              f'{factor_dir}/sig/{col}_sig.json'):
        if os.path.exists(p):
            data = json.load(open(p))
            label = data.get('label', '')
            if label:
                return label
    return col


def scan_factors():
    """扫描分析目录，所有有分析结果的因子全纳入。"""
    factors = set()
    for ic_file in glob.glob(f'{_output_dir()}/factor_analysis/*/*/ic/*_ic.json'):
        col = os.path.basename(ic_file).replace('_ic.json', '')
        cat = ic_file.split('/')[-4]
        factor_dir = f'{_output_dir()}/factor_analysis/{cat}/{col}'
        label = _parse_label(factor_dir, col)
        factors.add((col, label, cat))
    return list(factors)


def main():
    cfg = load_config()
    periods = get_periods(cfg)
    out_path = f'{_output_dir()}/result/factor_summary.csv'

    # 读已有汇总表（如果存在）
    old_rows = {}
    if os.path.exists(out_path):
        old_df = pd.read_csv(out_path)
        for _, row in old_df.iterrows():
            old_rows[(row['factor'], row['period'])] = row.to_dict()

    # 从 factors_config 读因子列表（而不是扫分析目录）
    factors = []
    if os.path.exists('config/factors_config.json'):
        fc = json.load(open('config/factors_config.json'))
        for domain, fdict in fc.items():
            for name, meta in fdict.items():
                factors.append((name, meta.get('label', ''), meta.get('cat', domain)))
    for col, label, cat in factors:
        for period_name, base_path in periods:
            factor_dir = f'{base_path}/{cat}/{col}'
            row = {'factor': col, 'label': label, 'cat': cat, 'period': period_name}
            row.update(read_ic(factor_dir, col))
            row.update(read_rr(factor_dir, col))
            row.update(read_sig(factor_dir, col))
            row.update(read_ret(factor_dir, col))
            key = (col, period_name)
            if len(row) > 4:  # 分析文件存在
                old_rows[key] = row
            elif key not in old_rows:  # 无数据且历史上也没有
                continue
            # 否则保留历史数据

    if not old_rows:
        print('无汇总数据')
        return

    df = pd.DataFrame(list(old_rows.values()))
    # 行列排序
    cat_order = {'pv': 0, 'fund': 1, 'ind': 2, 'monthly': 3}
    per_order = {'full': 0, 'bull': 1, 'bear': 2}
    df['_co'] = df['cat'].map(cat_order).fillna(9)
    df['_po'] = df['period'].map(per_order).fillna(9)
    df = df.sort_values(['_co', 'factor', '_po']).drop(columns=['_co', '_po'])

    # 固定列顺序
    col_order = ['factor', 'label', 'cat', 'period',
                 'ic_T1', 'icir_T1', 'ic_T5', 'icir_T5',
                 'ic_T10', 'icir_T10', 'ic_T22', 'icir_T22',
                 'long_win', 'short_win', 'long_odds', 'short_odds',
                 'ret_D1', 'ret_D10', 'ret_spread',
                 'kurtosis', 'acf1_mean', 'acf1_std']
    df = df[[c for c in col_order if c in df.columns]]

    # 胜率转百分数，其余数值保留四位小数
    pct_cols = {'long_win', 'short_win'}
    for c in df.columns:
        if c in ('factor', 'label', 'cat', 'period'):
            continue
        if c in pct_cols:
            df[c] = df[c] * 100
        df[c] = df[c].round(4)
    os.makedirs(f'{_output_dir()}/result', exist_ok=True)
    out_path = f'{_output_dir()}/result/factor_summary.csv'
    df.to_csv(out_path, index=False, float_format='%.4f', encoding='utf-8-sig')
    print(f'汇总表保存: {len(df)} 行, {len(df.columns)} 列 → {out_path}')


if __name__ == '__main__':
    main()
