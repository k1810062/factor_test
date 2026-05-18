"""
统一调度入口。读取 run_config.json，按配置执行因子计算 + 分析。
只计算选中的因子，跳过未选的。
"""
import pandas as pd
import json, sys, time, runpy

out_dir = 'output/data_processed'
analysis_dir = 'output/factor_analysis'

def load_config(path='industry/run_config.json'):
    with open(path) as f:
        return json.load(f)

def _try_read(path):
    """安全读 parquet，不存在返回 None。"""
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def compute_industry_factors(cfg):
    """按配置计算行业因子（增量追加，不覆盖旧列）。"""
    from factors_registry import FACTOR_FUNCTIONS
    selected = cfg.get('industry_factors', {})
    if not selected:
        return None

    factor_names = list(selected.keys())
    result = _try_read(f'{out_dir}/industry_daily_ratio.parquet')

    if result is None:
        print('=== 行业因子计算（首次）===\n')
        fac = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                              columns=['STOCK_CODE', 'TRADE_DATE', 'industry', 'industry_code'])
        result = fac[['industry_code', 'industry', 'TRADE_DATE']].drop_duplicates().reset_index(drop=True)
    else:
        print(f'=== 行业因子增量计算 ===')
        fac = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                              columns=['STOCK_CODE', 'TRADE_DATE', 'industry', 'industry_code'])

    mapping = fac[['STOCK_CODE', 'TRADE_DATE', 'industry', 'industry_code']].copy()

    existing = set(result.columns)
    for name in factor_names:
        ow = selected.get(name, {}).get('overwrite', [])
        if 'compute' in ow and name in existing:
            result = result.drop(columns=[name])
            existing.discard(name)

    to_compute = [n for n in factor_names if n not in existing]
    if not to_compute:
        print('  [跳过] 全部因子已存在')
        result.to_parquet(f'{out_dir}/industry_daily_ratio.parquet', index=False)
        return result

    print(f'  需计算: {to_compute}')
    from factors_registry import FACTOR_FUNCTIONS

    for name in to_compute:
        fn = FACTOR_FUNCTIONS.get(name)
        if fn is None:
            print(f'  [跳过] 未知因子: {name}')
            continue
        print(f'  Computing {name}...')
        t0 = time.time()
        col_data = fn(fac=fac, mapping=mapping, out_dir=out_dir)
        on_cols = [c for c in ['industry_code', 'TRADE_DATE'] if c in col_data.columns]
        result = result.merge(col_data, on=on_cols, how='left')
        print(f'    done ({time.time()-t0:.1f}s)')

    result.to_parquet(f'{out_dir}/industry_daily_ratio.parquet', index=False)
    total = len([c for c in result.columns if c not in ('industry_code', 'industry', 'TRADE_DATE')])
    print(f'行业因子保存: {len(result)} 行, 共 {total} 个因子列')
    return result


def compute_zscore():
    """从最新 industry_daily_ratio 生成截面 Z-score 表。"""
    df = pd.read_parquet(f'{out_dir}/industry_daily_ratio.parquet')
    factor_cols = [c for c in df.columns if c not in (
        'industry_code', 'industry', 'TRADE_DATE', 'ym', 'next_ret')]
    zdf = df[['industry_code', 'industry', 'TRADE_DATE']].copy()
    for col in factor_cols:
        zdf[col] = df.groupby('TRADE_DATE')[col].transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 0 else x * 0)
    zdf.to_parquet(f'{out_dir}/industry_daily_ratio_z.parquet', index=False)
    print(f'Z-score 表保存: {len(zdf)} 行, {len(factor_cols)} 个因子')


def compute_monthly_factors(cfg):
    """按配置计算月度因子（增量追加）。"""
    from factors_registry import FACTOR_FUNCTIONS
    selected = cfg.get('monthly_factors', {})
    if not selected:
        return None

    factor_names = list(selected.keys())
    result = _try_read(f'{out_dir}/industry_monthly_ratio.parquet')

    if result is None:
        print('=== 月度因子计算（首次）===\n')
        from factors_registry import base_monthly
        result = base_monthly(out_dir)
        ind_map = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                                   columns=['industry_code', 'industry'])
        ind_name_map = ind_map.drop_duplicates().set_index('industry_code')['industry']
        result['industry'] = result['industry_code'].map(ind_name_map)
    else:
        print('=== 月度因子增量计算 ===')

    existing = set(result.columns)
    for name in factor_names:
        ow = selected.get(name, {}).get('overwrite', [])
        if 'compute' in ow and name in existing:
            result = result.drop(columns=[name])
            existing.discard(name)

    to_compute = [n for n in factor_names if n not in existing]
    if not to_compute:
        print('  [跳过] 全部月度因子已存在')
        return result
    print(f'  需计算: {to_compute}')

    for name in to_compute:
        fn = FACTOR_FUNCTIONS.get(name)
        if fn is None:
            print(f'  [跳过] 未知因子: {name}')
            continue
        print(f'  Computing {name}...')
        t0 = time.time()
        col_data = fn(fac=None, mapping=None, out_dir=out_dir)
        result = result.merge(col_data, on=['industry_code', 'ym'], how='left')
        print(f'    done ({time.time()-t0:.1f}s)')

    cols = ['industry_code', 'industry', 'TRADE_DATE', 'ym']
    extra = [c for c in result.columns if c not in cols]
    result = result[cols + extra]
    result = result.sort_values(['industry_code', 'ym']).reset_index(drop=True)
    result.to_parquet(f'{out_dir}/industry_monthly_ratio.parquet', index=False)
    total = len(extra)
    print(f'月度因子保存: {len(result)} 行, 共 {total} 个因子列')
    return result


def run_analysis(cfg):
    """按配置运行分析脚本（同一进程内）。"""
    analysis = cfg.get('analysis', [])
    base = __file__.rsplit('/', 2)[0]  # factor_system 目录

    # 确保 analysis/ 在 sys.path 中，满足各脚本的 from analysis_base import ...
    analysis_dir = f'{base}/analysis'
    if analysis_dir not in sys.path:
        sys.path.insert(0, analysis_dir)

    scripts = {
        'charts': f'{base}/analysis/analyze_factors.py',
        'ic': f'{base}/analysis/analyze_factor_ic.py',
        'rr': f'{base}/analysis/analyze_factor_rr.py',
        'sig': f'{base}/analysis/analyze_factor_sig.py',
        'monthly': f'{base}/analysis/analyze_factor_monthly.py',
    }
    for name in analysis:
        script = scripts.get(name)
        if script:
            print(f'\n=== 运行 {name} 分析 ===')
            runpy.run_path(script, run_name='__main__')


def main():
    cfg = load_config()
    t0 = time.time()

    # 行业因子计算（已选才跑）
    if cfg.get('industry_factors'):
        compute_industry_factors(cfg)
        print('\n=== 截面 Z-score 标准化 ===')
        compute_zscore()

    # 月度因子计算（已选才跑）
    if cfg.get('monthly_factors'):
        compute_monthly_factors(cfg)

    # 分析（按配置跑）
    run_analysis(cfg)

    # 汇总
    print('\n=== 生成汇总表 ===')
    base = __file__.rsplit('/', 2)[0]
    runpy.run_path(f'{base}/analysis/summarize_results.py', run_name='__main__')

    print(f'\n全流程完成, 总耗时 {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
