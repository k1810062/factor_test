"""评价指标调度。按 domain_config 配置运行分析组。"""

import json
import os
import shutil
import glob
import pandas as pd
from config.domain_config import DOMAIN_CONFIG
from ..metrics.groups import ANALYSIS_GROUPS

# 分析组名称 → 输出子目录映射（用于跳过检查）
_GROUP_DIRS = {
    'ic': 'ic',
    'decile': 'ret',
    'sig': 'sig',
    'rr': 'rr',
    'ts': 'charts',
}


def _load_factors(factor_type):
    path = 'config/factors_config.json'
    if not os.path.exists(path):
        return {}
    return json.load(open(path)).get(factor_type, {})


def _get_overwrite(cfg, factor_type, col):
    src = _load_factors(factor_type)
    meta = src.get(col, {})
    ow = meta.get('overwrite', [])
    if ow:
        return ow
    if meta.get('mode') == 'overwrite':
        return ['ic', 'decile', 'sig', 'rr', 'ts']
    return []


def _get_freq_cfg(domain_cfg, freq):
    fc = domain_cfg.get(freq) if domain_cfg else None
    if fc is None:
        fc = domain_cfg.get('daily', {})
    return fc


def run_groups(cfg, factor_type, df, date_col='trade_date', base_dir=None):
    domain_cfg = DOMAIN_CONFIG.get(factor_type)
    if not domain_cfg:
        print(f'  [{factor_type}] 无 domain 配置，跳过分析')
        return
    if base_dir is None:
        base_dir = cfg.get('analysis_dir', {}).get(factor_type, f'output/analysis/{factor_type}')

    src = _load_factors(factor_type)
    factors = [(k, v['label'], v['cat'], v.get('freq', 'daily')) for k, v in src.items()]
    if not factors:
        print(f'  [{factor_type}] 无因子，跳过')
        return

    freq_groups = {}
    for _, _, _, freq in factors:
        fc = _get_freq_cfg(domain_cfg, freq)
        gs = tuple(fc.get('analysis_groups', []))
        freq_groups[freq] = gs
    all_groups = set()
    for gs in freq_groups.values():
        all_groups.update(gs)

    global_ow = cfg.get('analysis_overwrite', [])
    for group_name in all_groups:
        if group_name in global_ow:
            for col, _, cat, _ in factors:
                _dir = _GROUP_DIRS.get(group_name, group_name)
                for chk in glob.glob(f'{base_dir}*/{cat}/{col}/{_dir}'):
                    if os.path.isdir(chk):
                        shutil.rmtree(chk)
                        print(f'  [覆盖] {chk}')

    print(f'开始分析 {factor_type}，共 {len(factors)} 个因子')
    for group_name in all_groups:
        group_fn = ANALYSIS_GROUPS.get(group_name)
        if not group_fn:
            print(f'  [{factor_type}] 未知分析组: {group_name}')
            continue
        for col, cn, cat, freq in factors:
            fc = _get_freq_cfg(domain_cfg, freq)
            groups = fc.get('analysis_groups', [])
            if group_name not in groups:
                continue
            group_cfg = fc.get(group_name, {})
            factor_dir = f'{base_dir}/{cat}/{col}'
            chk = f'{factor_dir}/{_GROUP_DIRS.get(group_name, group_name)}'
            if group_name in _get_overwrite(cfg, factor_type, col):
                if os.path.exists(chk):
                    shutil.rmtree(chk)
                    print(f'  [{col}] overwrite {group_name}')
            if os.path.exists(chk) and os.listdir(chk):
                print(f'  [{col}] {group_name} 已分析，跳过')
                continue
            try:
                group_fn(df, col, cn, factor_dir, group_cfg, domain_cfg)
            except Exception as e:
                print(f'  [{col}] {group_name} 分析失败: {e}')
                import traceback
                traceback.print_exc()

    # 子区间分析
    sp = cfg.get('sub_period', {'from_file': 'data/market_periods.json',
                                 'groups': ['bull', 'bear', 'consolidate']})
    if 'from_file' in sp:
        ext = json.load(open(sp['from_file']))
        names = sp.get('groups', list(ext.keys()))
        sp = {'groups': [ext[name] for name in names]}
    groups_sub = sp.get('groups', [sp] if sp else [])
    for group in groups_sub:
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
        key_col = domain_cfg['key_col']
        df_sub = pd.concat(segments).sort_values([key_col, date_col]).reset_index(drop=True)

        if len(df_sub) == 0:
            print(f'  [{suffix}] 无数据，跳过')
            continue

        sub_dir = f'{base_dir}_{suffix}'
        os.makedirs(sub_dir, exist_ok=True)
        print(f'\n=== 子区间分析：{suffix} ===')
        for group_name in all_groups:
            group_fn = ANALYSIS_GROUPS.get(group_name)
            if not group_fn:
                continue
            for col, cn, cat, freq in factors:
                fc = _get_freq_cfg(domain_cfg, freq)
                groups = fc.get('analysis_groups', [])
                if group_name not in groups:
                    continue
                group_cfg = fc.get(group_name, {})
                factor_dir = f'{sub_dir}/{cat}/{col}'
                chk = f'{factor_dir}/{_GROUP_DIRS.get(group_name, group_name)}'
                if group_name in _get_overwrite(cfg, factor_type, col):
                    if os.path.exists(chk):
                        shutil.rmtree(chk)
                if os.path.exists(chk) and os.listdir(chk):
                    continue
                try:
                    group_fn(df_sub, col, cn, factor_dir, group_cfg, domain_cfg)
                except Exception as e:
                    print(f'  [{col}] {group_name} 子区间分析失败: {e}')

    print(f'\n{domain_cfg["key_col"]} 域分析完成！结果保存在 {base_dir}/')
