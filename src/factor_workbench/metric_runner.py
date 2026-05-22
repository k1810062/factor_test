"""评价指标调度。替代 analysis/analysis_base.py 和 analyze_all.py。"""

import json
import os
import shutil
import glob
import pandas as pd
from .registry import get_metrics


def _get_overwrite(cfg, factor_type, col):
    src = cfg.get(factor_type) or cfg.get(f'{factor_type}_factors', {})
    return src.get(col, {}).get('overwrite', [])


def run_metrics(cfg, factor_type, df, date_col='TRADE_DATE', check_subdir=None):
    """对所有因子运行配置中的评价指标（串行）。"""
    analysis_dir = cfg.get('analysis_dir', 'output/factor_analysis')
    base_dir = os.path.dirname(analysis_dir)

    src = cfg.get(factor_type) or cfg.get(f'{factor_type}_factors', {})
    factors = [(k, v['label'], v['cat']) for k, v in src.items()]
    if not factors:
        return

    meta = get_metrics().get(check_subdir)
    if meta is None:
        return

    # 全局覆盖
    global_ow = cfg.get('analysis_overwrite', [])
    if check_subdir and check_subdir in global_ow:
        for col, _, cat in factors:
            for chk in glob.glob(f'{base_dir}/factor_analysis*/{cat}/{col}/{check_subdir}'):
                if os.path.isdir(chk):
                    shutil.rmtree(chk)
                    print(f'  [覆盖] {os.path.relpath(chk, base_dir)}')

    def _skip_factor(d, col):
        chk = f'{d}/{check_subdir}' if check_subdir else d
        if check_subdir and check_subdir in _get_overwrite(cfg, factor_type, col):
            if os.path.exists(chk):
                shutil.rmtree(chk)
                print(f'  [{col}] overwrite {check_subdir}')
        return os.path.exists(chk) and os.listdir(chk)

    # ---- 全量分析 ----
    print(f'开始分析，共 {len(factors)} 个因子\n')
    for col, cn, cat in factors:
        factor_dir = f'{analysis_dir}/{cat}/{col}'
        if _skip_factor(factor_dir, col):
            print(f'  [{col}] 已分析，跳过')
            continue
        meta.fn(df, col, cn, cat, factor_dir)
        print(f'  [{col}] 完成')

    # ---- 子区间分析 ----
    sp = cfg.get('sub_period', {'from_file': 'data/market_periods.json',
                                 'groups': ['bull', 'bear', 'consolidate']})
    if 'from_file' in sp:
        ext = json.load(open(sp['from_file']))
        names = sp.get('groups', list(ext.keys()))
        sp = {'groups': [ext[name] for name in names]}
    groups = sp.get('groups', [sp] if sp else [])
    for group in groups:
        ranges = []
        if isinstance(group, dict):
            if 'ranges' in group:
                ranges = group['ranges']
                suffix = group.get('suffix', '_'.join(str(i + 1) for i in range(len(ranges))))
            elif group.get('start') and group.get('end'):
                ranges = [group]
                suffix = f'{group["start"]}_{group["end"]}'
        if not ranges:
            continue

        segments = []
        for r in ranges:
            start = r.get('start', 'beginning')
            end = r.get('end', 'now')
            if start == 'beginning':
                start = df[date_col].min()
            if end == 'now':
                end = df[date_col].max()
            if date_col == 'ym':
                seg = df[(df[date_col] >= start[:6]) & (df[date_col] <= end[:6])]
            else:
                seg = df[(df[date_col] >= start) & (df[date_col] <= end)]
            segments.append(seg)
        df_sub = pd.concat(segments).sort_values(
            ['industry_code', date_col]).reset_index(drop=True)

        if len(df_sub) == 0:
            print(f'  [{suffix}] 无数据，跳过')
            continue

        sub_dir = f'{base_dir}/factor_analysis_{suffix}'
        os.makedirs(sub_dir, exist_ok=True)
        print(f'\n=== 子区间分析：{suffix} ===')
        for col, cn, cat in factors:
            factor_dir = f'{sub_dir}/{cat}/{col}'
            if _skip_factor(factor_dir, col):
                print(f'  [{col}] 已分析，跳过')
                continue
            meta.fn(df_sub, col, cn, cat, factor_dir)
            print(f'  [{col}] 完成')

    print(f'\n全部完成！结果保存在 {analysis_dir}/')
