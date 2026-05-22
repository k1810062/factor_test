"""月度因子函数库。每个因子加 @factor 装饰器，通过 api 取数。

返回带 key 列（industry_code, ym）+ 因子列的 DataFrame。
"""

import pandas as pd
import numpy as np
from factor_workbench.registry import factor


@factor(name='ret_T1', category='monthly', label='次月收益率', domain='monthly', published=False)
def ret_T1(api):
    """基表：月末指数收盘价 + 次月收益率。"""
    swidx = api.table('swi_daily', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE']).rename(
        columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
    swidx = swidx.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    swidx['ym'] = swidx['TRADE_DATE'].str[:6]
    monthly = swidx.groupby(['industry_code', 'ym']).tail(1).copy()
    monthly = monthly.sort_values(['industry_code', 'ym']).reset_index(drop=True)
    monthly['ret_T1'] = monthly.groupby('industry_code')['idx_close'].transform(
        lambda x: x.shift(-1) / x - 1)
    return monthly[['industry_code', 'ym', 'ret_T1']]


@factor(name='upg_cnt_rt', category='monthly', label='上调数量占比', domain='monthly')
def upg_cnt_rt(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'RATING_GRADE'])
    stock = stock[stock['RATING_GRADE'].notna()].copy()
    stock['ym'] = stock['TRADE_DATE'].str[:6]

    def agg(g):
        total = len(g)
        up_cnt = (g['RATING_GRADE'] == 1).sum()
        return up_cnt / total if total > 0 else 0

    return stock.groupby(['industry_code', 'ym']).apply(agg, include_groups=False).reset_index(name='upg_cnt_rt')


@factor(name='upg_mv_rt', category='monthly', label='上调市值占比', domain='monthly')
def upg_mv_rt(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'RATING_GRADE', 'VAL_MV'])
    stock = stock[stock['RATING_GRADE'].notna()].copy()
    stock['ym'] = stock['TRADE_DATE'].str[:6]

    def agg(g):
        total_mv = g['VAL_MV'].sum()
        up_mv = g.loc[g['RATING_GRADE'] == 1, 'VAL_MV'].sum()
        return up_mv / total_mv if total_mv > 0 else 0

    return stock.groupby(['industry_code', 'ym']).apply(agg, include_groups=False).reset_index(name='upg_mv_rt')


@factor(name='roe_pctl', category='monthly', label='盈利景气度', domain='monthly')
def roe_pctl(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'ROE_TTM', 'MV'])
    mapping = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code'])
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    stock = stock.dropna(subset=['ROE_TTM', 'MV'])
    stock['ym'] = stock['TRADE_DATE'].str[:6]
    roe = stock.groupby(['industry_code', 'ym']).apply(
        lambda g: np.average(g['ROE_TTM'], weights=g['MV']), include_groups=False
    ).reset_index(name='roe').sort_values(['industry_code', 'ym']).reset_index(drop=True)
    roe['roe_pctl'] = roe.groupby('industry_code')['roe'].transform(
        lambda x: x.rolling(36, min_periods=12).apply(
            lambda s: (s <= s.iloc[-1]).sum() / len(s)))
    return roe[['industry_code', 'ym', 'roe_pctl']]


@factor(name='mom_12m_m', category='monthly', label='月度动量因子', domain='monthly')
def mom_12m_m(api):
    swidx = api.table('swi_daily', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE']).rename(
        columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
    swidx = swidx.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    swidx['ym'] = swidx['TRADE_DATE'].str[:6]
    monthly = swidx.groupby(['industry_code', 'ym']).tail(1).copy()
    monthly = monthly.sort_values(['industry_code', 'ym']).reset_index(drop=True)
    monthly['mom_12m_m'] = monthly.groupby('industry_code')['idx_close'].transform(
        lambda x: x.shift(1) / x.shift(12) - 1)
    return monthly[['industry_code', 'ym', 'mom_12m_m']]


# ─── 新增草稿因子 ───
@factor(name='roe_improve', category='monthly', label='盈利景气改善', domain='monthly')
def roe_improve(api):
    df = api.table('industry_monthly', columns=['industry_code', 'ym', 'roe_pctl'])
    df = df.sort_values(['industry_code', 'ym'])
    df['roe_improve'] = df.groupby('industry_code')['roe_pctl'].diff(1)
    return df[['industry_code', 'ym', 'roe_improve']]
