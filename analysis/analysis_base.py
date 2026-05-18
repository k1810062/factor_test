"""分析脚本共享框架。封装配置读取、因子循环、子区间多组管理等公共逻辑。"""
import pandas as pd
import json, os, shutil


def load_config():
    with open('industry/run_config.json') as f:
        return json.load(f)


_cfg = load_config()


def get_factors(factor_type='industry'):
    """返回 [(列名, 中文名, 分类)]。"""
    src = _cfg.get(f'{factor_type}_factors', {})
    return [(k, v['label'], v['cat']) for k, v in src.items()]


def _get_overwrite(factor_type, col):
    """读取因子配置中的 overwrite 列表。"""
    src = _cfg.get(f'{factor_type}_factors', {})
    return src.get(col, {}).get('overwrite', [])


def run_analysis(df, factor_fn, factor_type='industry', date_col='TRADE_DATE',
                 check_subdir=None):
    """
    通用分析框架。
    df: 全量数据
    factor_fn(df_sub, col, cn, cat, output_dir): 单个因子的分析函数
    factor_type: 'industry' 或 'monthly'
    date_col: 日期列名，默认 TRADE_DATE，monthly 用 ym
    check_subdir: 增量检查的二级目录（如 'ic'），避免各分析脚本误判
    """
    factors = get_factors(factor_type)
    out_dir = 'output'
    analysis_dir = f'{out_dir}/factor_analysis'

    def _skip_factor(d, col):
        chk = f'{d}/{check_subdir}' if check_subdir else d
        # overwrite：删掉该分析类型的子目录
        if check_subdir and check_subdir in _get_overwrite(factor_type, col):
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
        factor_fn(df, col, cn, cat, factor_dir)

    # ---- 子区间多组分析（支持外部文件引用） ----
    sp = _cfg.get('sub_period', {})
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
                suffix = group.get('suffix', '_'.join(str(i+1) for i in range(len(ranges))))
            elif group.get('start') and group.get('end'):
                ranges = [group]
                suffix = f'{group["start"]}_{group["end"]}'
        if not ranges:
            continue

        # 多段拼接（支持 "now" 表示至今，"beginning" 表示数据起点）
        segments = []
        for r in ranges:
            start = r.get('start', 'beginning')
            end = r.get('end', 'now')
            if start == 'beginning': start = df[date_col].min()
            if end == 'now': end = df[date_col].max()
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

        sub_dir = f'{out_dir}/factor_analysis_{suffix}'
        os.makedirs(sub_dir, exist_ok=True)
        print(f'\n=== 子区间分析：{suffix} ===')
        for col, cn, cat in factors:
            factor_dir = f'{sub_dir}/{cat}/{col}'
            if _skip_factor(factor_dir, col):
                print(f'  [{col}] 已分析，跳过')
                continue
            factor_fn(df_sub, col, cn, cat, factor_dir)

    print(f'\n全部完成！结果保存在 {analysis_dir}/')
