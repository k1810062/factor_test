"""个股因子调度器。读取配置，计算选中的个股因子，增量追加到 factor_stock.parquet。"""
import pandas as pd
import json, os, sys

data_dir = 'data'
out_dir = 'output/data_processed'
import os
os.makedirs(out_dir, exist_ok=True)

def load_config():
    with open('stock/stock_config.json') as f:
        return json.load(f)


def _try_read(path):
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def main():
    cfg = load_config()
    selected = cfg.get('stock_factors', {})
    if not selected:
        print('无个股因子配置，跳过')
        return

    from stock_factors_registry import STOCK_FACTORS
    factor_names = list(selected.keys())

    # 读基础数据
    df = pd.read_parquet(f'{data_dir}/stock_base.parquet')
    df = df.sort_values(['STOCK_CODE', 'TRADE_DATE']).reset_index(drop=True)
    print(f'基础数据: {len(df)} 行')

    # 读已有因子表
    result = _try_read(f'{out_dir}/factor_stock.parquet')
    if result is not None:
        print(f'已有因子表: {len(result.columns)} 列')
        existing = set(result.columns)
    else:
        result = df[['STOCK_CODE', 'TRADE_DATE', 'industry', 'industry_code']].copy()
        existing = set()

    # overwrite / skip 判断
    need_compute = []
    for name in factor_names:
        mode = selected.get(name, {}).get('mode', 'skip')
        if mode == 'overwrite' and name in existing:
            result = result.drop(columns=[name])
            existing.discard(name)
            print(f'  [{name}] overwrite')
        if name not in existing:
            need_compute.append(name)

    if not need_compute:
        print('  [跳过] 全部因子已存在')
        result.to_parquet(f'{out_dir}/factor_stock.parquet', index=False)
        return

    print(f'  需计算: {need_compute}')

    for name in need_compute:
        fn = STOCK_FACTORS.get(name)
        if fn is None:
            print(f'  [跳过] 未知因子: {name}')
            continue
        print(f'  Computing {name}...')
        t0 = __import__('time').time()
        values = fn(df)
        result[name] = values
        print(f'    done ({__import__("time").time()-t0:.1f}s)')

    result.to_parquet(f'{out_dir}/factor_stock.parquet', index=False)
    total = len([c for c in result.columns if c not in ('STOCK_CODE', 'TRADE_DATE', 'industry', 'industry_code')])
    print(f'因子表保存: {len(result)} 行, {total} 个因子')


if __name__ == '__main__':
    main()
