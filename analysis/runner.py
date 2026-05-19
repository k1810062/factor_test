"""分析调度入口：统一数据加载 + 分析调度。"""
import pandas as pd
import os

data_dir = 'output/data_processed'


def load_industry_factors():
    """加载行业因子数据 + 计算 forward return。"""
    df = pd.read_parquet(f'{data_dir}/industry_daily_ratio.parquet')
    idx = pd.read_parquet('data/SWI_daily.parquet',
                          columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
    idx = idx.rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
    df = df.merge(idx, on=['industry_code', 'TRADE_DATE'], how='inner')
    df = df.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)

    g = df.groupby('industry_code')['idx_close']
    for h in [1, 5, 10, 22]:
        df[f'ret_T{h}'] = g.transform(lambda x: x.shift(-h) / x - 1)
    return df


def load_monthly_factors():
    """加载月度因子数据（ret_T1 已在表中）。"""
    return pd.read_parquet(f'{data_dir}/industry_monthly_ratio.parquet')


def load_data(factor_type):
    """统一数据加载入口。"""
    if factor_type == 'monthly':
        return load_monthly_factors()
    return load_industry_factors()
