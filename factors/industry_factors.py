"""行业日度因子函数库。每个因子加 @factor 装饰器，通过 api 取数。

返回带 key 列（industry_code, TRADE_DATE）+ 因子列的 DataFrame。
"""

import pandas as pd
import numpy as np
from math import ceil
from factor_workbench.registry import factor


def _mapping(api):
    """取行业映射（STOCK_CODE → industry_code）。"""
    return api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code'])


def _swi_idx(api):
    """取行业指数日线。"""
    return api.table('swi_daily', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE']).rename(
        columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})


# ─── 8 个简单均值因子 ───

@factor(name='up_ratio', category='pv', label='上涨家数占比', domain='industry')
def up_ratio(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'up_stock'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['up_stock'].mean().reset_index(name='up_ratio')


@factor(name='strong_ratio', category='pv', label='强势股涨幅占比', domain='industry')
def strong_ratio(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'strong_stock'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['strong_stock'].mean().reset_index(name='strong_ratio')


@factor(name='vol_ratio', category='pv', label='强势成交量占比', domain='industry')
def vol_ratio(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'strong_volume'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['strong_volume'].mean().reset_index(name='vol_ratio')


@factor(name='ma8_pos_avg', category='pv', label='8日均线多头占比', domain='industry')
def ma8_pos_avg(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'ma8_pos'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['ma8_pos'].mean().reset_index(name='ma8_pos_avg')


@factor(name='tech_sync_rt', category='pv', label='技术指标同步率', domain='industry')
def tech_sync_rt(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'tech_sync'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['tech_sync'].mean().reset_index(name='tech_sync_rt')


@factor(name='break_cons_rt', category='pv', label='突破整理形态占比', domain='industry')
def break_cons_rt(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'break_cons'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['break_cons'].mean().reset_index(name='break_cons_rt')


@factor(name='ma_bull', category='pv', label='多头均线占比', domain='industry')
def ma_bull(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'ma_bull'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['ma_bull'].mean().reset_index()


@factor(name='ma_bear', category='pv', label='空头均线占比', domain='industry')
def ma_bear(api):
    fac = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code', 'ma_bear'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['ma_bear'].mean().reset_index()


@factor(name='ma5_ratio', category='pv', label='MA5上方占比', domain='industry')
def ma5_ratio(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
    mapping = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code'])
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    stock = stock.sort_values(['STOCK_CODE', 'TRADE_DATE'])
    ma5 = stock.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(5).mean())
    stock['above_ma5'] = (stock['CLOSE'] > ma5).astype(int)
    return stock.groupby(['industry_code', 'TRADE_DATE'])['above_ma5'].mean().reset_index(name='ma5_ratio')


# ─── 10 个复杂因子（读原始数据） ───

@factor(name='strong_fund_ratio', category='fund', label='强势股资金占比', domain='industry')
def strong_fund_ratio(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'AMOUNT'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')

    def _fund_ratio(g):
        cnt = max(ceil(len(g) * 0.1), 1)
        return g.nlargest(cnt, 'AMOUNT')['AMOUNT'].sum() / g['AMOUNT'].sum()

    return stock.groupby(['industry_code', 'TRADE_DATE'], group_keys=False).apply(
        _fund_ratio, include_groups=False).reset_index(name='strong_fund_ratio')


@factor(name='turn_pctl', category='ind', label='换手率分位数', domain='industry')
def turn_pctl(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'TURN', 'MV'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['TURN', 'MV'])
    ind_turn = stock.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: np.average(g['TURN'], weights=g['MV']), include_groups=False
    ).reset_index(name='ind_turn').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)

    def _pctl_250(s):
        if len(s) < 20:
            return np.nan
        return (s.iloc[:-1] < s.iloc[-1]).sum() / (len(s) - 1)

    ind_turn['turn_pctl'] = ind_turn.groupby('industry_code')['ind_turn'].transform(
        lambda x: x.rolling(250, min_periods=20).apply(_pctl_250))
    return ind_turn[['industry_code', 'TRADE_DATE', 'turn_pctl']]


@factor(name='diverge_5d', category='fund', label='主力资金背离度', domain='industry')
def diverge_5d(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'INFLOW_RATE', 'MV'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['INFLOW_RATE', 'MV'])
    ind_inflow = stock.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: np.average(g['INFLOW_RATE'], weights=g['MV']), include_groups=False
    ).reset_index(name='ind_inflow').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_inflow['inflow_5d'] = ind_inflow.groupby('industry_code')['ind_inflow'].transform(lambda x: x.rolling(5).sum())

    swidx = _swi_idx(api).sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    swidx['ret_5d'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(5) - 1)
    diverge = ind_inflow.merge(swidx[['industry_code', 'TRADE_DATE', 'ret_5d']],
                                on=['industry_code', 'TRADE_DATE'], how='left')
    diverge['diverge_5d'] = diverge['inflow_5d'] - diverge['ret_5d']
    return diverge[['industry_code', 'TRADE_DATE', 'diverge_5d']]


@factor(name='ret_divg', category='ind', label='涨幅分化度', domain='industry')
def ret_divg(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE', 'MV'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['CLOSE', 'MV'])
    stock = stock.sort_values(['STOCK_CODE', 'TRADE_DATE']).reset_index(drop=True)
    stock['stock_ret'] = stock.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x / x.shift(1) - 1)
    top3_ret = stock.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: g.nlargest(3, 'MV')['stock_ret'].mean(), include_groups=False
    ).reset_index(name='top3_ret')

    swidx = _swi_idx(api).sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    swidx['idx_ret'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(1) - 1)
    ret = top3_ret.merge(swidx[['industry_code', 'TRADE_DATE', 'idx_ret']],
                          on=['industry_code', 'TRADE_DATE'], how='left')
    ret['ret_divg'] = ret['top3_ret'] - ret['idx_ret']
    return ret[['industry_code', 'TRADE_DATE', 'ret_divg']]


@factor(name='amt_divg', category='fund', label='成交占比乖离率', domain='industry')
def amt_divg(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'AMOUNT'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['AMOUNT'])
    total_amt = stock.groupby('TRADE_DATE')['AMOUNT'].sum().reset_index(name='total_amt')
    ind_amt = stock.groupby(['industry_code', 'TRADE_DATE'])['AMOUNT'].sum().reset_index(name='ind_amt')
    amt = ind_amt.merge(total_amt, on='TRADE_DATE', how='left')
    amt['amt_ratio'] = amt['ind_amt'] / amt['total_amt']
    amt = amt.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    amt['amt_ma20'] = amt.groupby('industry_code')['amt_ratio'].transform(lambda x: x.rolling(20).mean())
    amt['amt_divg'] = amt['amt_ratio'] / amt['amt_ma20'] - 1
    return amt[['industry_code', 'TRADE_DATE', 'amt_divg']]


@factor(name='margin_dir', category='fund', label='融资盘方向', domain='industry')
def margin_dir(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'BORROW_BUY', 'BORROW_REPAY'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['BORROW_BUY', 'BORROW_REPAY'])
    stock['net_margin'] = stock['BORROW_BUY'] - stock['BORROW_REPAY']
    ind = stock.groupby(['industry_code', 'TRADE_DATE'])['net_margin'].sum().reset_index()
    ind = ind.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind['chg_rt'] = ind.groupby('industry_code')['net_margin'].transform(lambda x: x / x.shift(1) - 1)
    ind['margin_dir'] = ind.groupby('industry_code')['chg_rt'].transform(lambda x: x.rolling(3).mean())
    return ind[['industry_code', 'TRADE_DATE', 'margin_dir']]


@factor(name='margin_sum5', category='fund', label='融资净买入5日滚动', domain='industry')
def margin_sum5(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'BORROW_BUY', 'BORROW_REPAY'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['BORROW_BUY', 'BORROW_REPAY'])
    stock['net_margin'] = stock['BORROW_BUY'] - stock['BORROW_REPAY']
    ind = stock.groupby(['industry_code', 'TRADE_DATE'])['net_margin'].sum().reset_index()
    ind = ind.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind['margin_sum5'] = ind.groupby('industry_code')['net_margin'].transform(lambda x: x.rolling(5).sum())
    return ind[['industry_code', 'TRADE_DATE', 'margin_sum5']]


@factor(name='pb_disp', category='ind', label='估值离散度', domain='industry')
def pb_disp(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'MV', 'NET_ASSET_VALUE'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['MV', 'NET_ASSET_VALUE'])
    stock = stock.sort_values(['STOCK_CODE', 'TRADE_DATE']).reset_index(drop=True)
    ind_pb = stock.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: g['MV'].sum() / g['NET_ASSET_VALUE'].sum(), include_groups=False
    ).reset_index(name='ind_pb').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_pb['pb_pctl'] = ind_pb.groupby('industry_code')['ind_pb'].transform(
        lambda x: x.rolling(1250, min_periods=250).apply(
            lambda s: (s <= s.iloc[-1]).sum() / len(s) if len(s) >= 20 else np.nan))
    ind_pb['pb_disp'] = ind_pb.groupby('industry_code')['pb_pctl'].transform(lambda x: x.rolling(20).std())
    return ind_pb[['industry_code', 'TRADE_DATE', 'pb_disp']]


@factor(name='etf_inflow_st', category='fund', label='行业ETF净流入5日平滑', domain='industry')
def etf_inflow_st(api):
    df = api.table('etf_daily')
    df['TRADE_DT'] = df['TRADE_DT'].astype(str)
    ind = df.groupby(['INDUSTRY_CODE', 'TRADE_DT'])['净流入金额（万元）'].sum().reset_index()
    ind = ind.rename(columns={'INDUSTRY_CODE': 'industry_code', 'TRADE_DT': 'TRADE_DATE', '净流入金额（万元）': 'inflow_amt'})
    ind = ind.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind['etf_inflow_st'] = ind.groupby('industry_code')['inflow_amt'].transform(lambda x: x.rolling(5).mean())
    return ind[['industry_code', 'TRADE_DATE', 'etf_inflow_st']]


@factor(name='mom_12m', category='ind', label='动量因子', domain='industry')
def mom_12m(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (LAG(CLOSE, 21) OVER w / LAG(CLOSE, 252) OVER w - 1) as mom_12m
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)

# ─── 新增草稿因子 ───

@factor(name='pct_5d', category='pv', label='5日涨幅', domain='industry')
def pct_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as pct_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)


# ─── 新增草稿因子 ───
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)


# ─── 新增草稿因子 ───
@factor(name='ma_5d', category='pv', label='5日涨幅', domain='industry')
def ma_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ma_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)

@factor(name='ma_10d', category='pv', label='10日涨幅', domain='industry')
def ma_10d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 10) OVER w - 1) as ma_10d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)


# ─── 新增草稿因子 ───
@factor(name='ma_5d', category='pv', label='5日涨幅', domain='industry')
def ma_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ma_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)

@factor(name='ma_10d', category='pv', label='10日涨幅', domain='industry')
def ma_10d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 10) OVER w - 1) as ma_10d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)


# ─── 新增草稿因子 ───
@factor(name='bull_bear_spread', category='ind', label='多空均线差', domain='industry')
def bull_bear_spread(api):
    return api.query("""
        SELECT industry_code, TRADE_DATE,
               (ma_bull - ma_bear) as bull_bear_spread
        FROM industry_daily
    """)
    
@factor(name='roe_improve', category='monthly', label='盈利景气改善', domain='monthly')
def roe_improve(api):
    df = api.table('industry_monthly', columns=['industry_code', 'ym', 'roe_pctl'])
    df = df.sort_values(['industry_code', 'ym'])
    df['roe_improve'] = df.groupby('industry_code')['roe_pctl'].diff(1)
    return df[['industry_code', 'ym', 'roe_improve']]


# ─── 新增草稿因子 ───
@factor(name='bull_bear_spread', category='ind', label='多空均线差', domain='industry')
def bull_bear_spread(api):
    return api.query("""
        SELECT industry_code, TRADE_DATE,
               (ma_bull - ma_bear) as bull_bear_spread
        FROM industry_daily
    """)
    
@factor(name='roe_improve', category='monthly', label='盈利景气改善', domain='monthly')
def roe_improve(api):
    df = api.table('industry_monthly', columns=['industry_code', 'ym', 'roe_pctl'])
    df = df.sort_values(['industry_code', 'ym'])
    df['roe_improve'] = df.groupby('industry_code')['roe_pctl'].diff(1)
    return df[['industry_code', 'ym', 'roe_improve']]
