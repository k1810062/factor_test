"""逐 domain 汇总因子分析结果到各自 CSV。"""
import pandas as pd
import json, os, glob


def load_config():
    path = 'config/config.json'
    if not os.path.exists(path):
        path = 'industry/run_config.json'
    with open(path) as f:
        return json.load(f)


def get_periods(analysis_dir):
    """返回 [(周期名, 分析目录), ...]"""
    periods = [('full', analysis_dir)]
    cfg = load_config()
    sp = cfg.get('sub_period', {})
    if 'from_file' in sp:
        ext = json.load(open(sp['from_file']))
        names = sp.get('groups', list(ext.keys()))
        for name in names:
            suffix = ext[name]['suffix']
            periods.append((suffix, f'{analysis_dir}_{suffix}'))
    return periods


def read_ic(factor_dir, col):
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
    path = f'{factor_dir}/rr/{col}_rr.json'
    if not os.path.exists(path):
        return {}
    return json.load(open(path))


def read_sig(factor_dir, col):
    path = f'{factor_dir}/sig/{col}_sig.json'
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    return {
        'kurtosis': data.get('excess_kurt', data.get('kurtosis', 0)),
        'acf1_mean': data.get('acf1_mean', 0),
        'acf1_std': data.get('acf1_std', 0),
    }


def read_ret(factor_dir, col):
    path = f'{factor_dir}/ret/{col}_ret.json'
    if not os.path.exists(path):
        return {}
    return json.load(open(path))


def summarize_domain(domain, factors_cfg, analysis_dir, out_dir):
    """为一个 domain 生成汇总 CSV（增量：保留旧行，有新分析数据则更新）。"""
    periods = get_periods(analysis_dir)

    # 读已有 CSV（保留旧因子数据）
    out_path = f'{out_dir}/{domain}_factor_summary.csv'
    rows = {}
    if os.path.exists(out_path):
        old_df = pd.read_csv(out_path)
        for _, r in old_df.iterrows():
            rows[(r['factor'], r['period'])] = r.to_dict()

    # 遍历当前配置中的因子，有分析数据则更新
    for col, meta in factors_cfg.items():
        label = meta.get('label', col)
        cat = meta.get('cat', domain)
        for period_name, base_path in periods:
            factor_dir = f'{base_path}/{cat}/{col}'
            row = {'factor': col, 'label': label, 'cat': cat, 'period': period_name}
            row.update(read_ic(factor_dir, col))
            row.update(read_rr(factor_dir, col))
            row.update(read_sig(factor_dir, col))
            row.update(read_ret(factor_dir, col))
            key = (col, period_name)
            if len(row) > 4:
                rows[key] = row
            elif key not in rows:
                continue  # 无旧数据也无新数据，跳过

    if not rows:
        print(f'  [{domain}] 无数据')
        return

    df = pd.DataFrame(list(rows.values()))
    cat_order = {'pv': 0, 'fund': 1, 'ind': 2, 'monthly': 3}
    per_order = {'full': 0, 'bull': 1, 'bear': 2}
    df['_co'] = df['cat'].map(cat_order).fillna(9)
    df['_po'] = df['period'].map(per_order).fillna(9)
    df = df.sort_values(['_co', 'factor', '_po']).drop(columns=['_co', '_po'])

    col_order = ['factor', 'label', 'cat', 'period',
                 'ic_T1', 'icir_T1', 'ic_T5', 'icir_T5',
                 'ic_T10', 'icir_T10', 'ic_T22', 'icir_T22',
                 'long_win', 'short_win', 'long_odds', 'short_odds',
                 'ret_D1', 'ret_D10', 'ret_spread',
                 'kurtosis', 'acf1_mean', 'acf1_std']
    df = df[[c for c in col_order if c in df.columns]]

    for c in df.columns:
        if c not in ('factor', 'label', 'cat', 'period'):
            df[c] = pd.to_numeric(df[c]).round(4)

    os.makedirs(out_dir, exist_ok=True)
    out_path = f'{out_dir}/{domain}_factor_summary.csv'
    df.to_csv(out_path, index=False, float_format='%.4f', encoding='utf-8-sig')
    print(f'  [{domain}] {len(df)} 行 → {out_path}')


def main():
    cfg = load_config()
    analysis_cfg = cfg.get('analysis_dir', {})
    fc_path = 'config/factors_config.json'

    if not os.path.exists(fc_path):
        print('无 factors_config.json')
        return

    fc = json.load(open(fc_path))
    out_dir = 'output/result'

    print('生成汇总表:')
    for domain, factors_cfg in fc.items():
        analysis_dir = analysis_cfg.get(domain) if isinstance(analysis_cfg, dict) else f'output/analysis/{domain}'
        if not analysis_dir:
            print(f'  [{domain}] 无分析目录配置')
            continue
        summarize_domain(domain, factors_cfg, analysis_dir, out_dir)


if __name__ == '__main__':
    main()
