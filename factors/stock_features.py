"""个股因子函数库。每个因子加 @factor 装饰器，通过 api 取数。

每个因子返回带 key 列（STOCK_CODE, TRADE_DATE）+ 因子列的 DataFrame。
"""

import pandas as pd
import numpy as np
from factor_workbench.registry import factor


def _fib_ma(df, n):
    return df.groupby('stock_code')['close'].transform(lambda x: x.rolling(n).mean())


@factor(name='up_stock', category='pv', label='当日是否上涨', domain='stock', published=False)
def up_stock(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    close_diff = df.groupby('stock_code')['close'].diff()
    result = np.where(close_diff.notna(), (close_diff > 0).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(up_stock=result)


@factor(name='strong_stock', category='pv', label='收盘价>60日均线', domain='stock', published=False)
def strong_stock(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma60 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(60).mean())
    result = np.where(pd.notna(ma60), (df['close'] > ma60).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(strong_stock=result)


@factor(name='strong_volume', category='pv', label='成交量异常放大', domain='stock', published=False)
def strong_volume(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'vol'])
    g = df.groupby('stock_code')['vol']
    s20 = g.transform(lambda x: x.rolling(20).sum())
    min20 = g.transform(lambda x: x.rolling(20).min())
    max20 = g.transform(lambda x: x.rolling(20).max())
    cnt20 = g.transform(lambda x: x.rolling(20).count())
    trim_mean = np.where(cnt20 >= 3, (s20 - min20 - max20) / (cnt20 - 2), np.nan)
    result = np.where(pd.notna(trim_mean), (df['vol'] / trim_mean > 1.06).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(strong_volume=result)


@factor(name='ma8_pos', category='pv', label='均线位置评分', domain='stock', published=False)
def ma8_pos(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    fibs = [8, 13, 21, 34, 55, 89, 144, 233]
    ma_cols = []
    for n in fibs:
        col = f'_ma{n}'
        df[col] = _fib_ma(df, n)
        ma_cols.append(col)
    vals = df[['close'] + ma_cols].values
    ranks = vals.argsort(axis=1).argsort(axis=1) + 1
    close_rank = ranks[:, 0]
    result = np.select([close_rank <= 3, close_rank <= 6], [-1, 0], default=1)
    has_all = pd.DataFrame({c: df[c].notna() for c in ma_cols}).all(axis=1).values
    result = np.where(has_all, result, np.nan).astype(float)
    for c in ma_cols:
        df.drop(columns=[c], inplace=True)
    return df[['stock_code', 'trade_date']].assign(ma8_pos=result)


@factor(name='tech_sync', category='pv', label='技术指标同步', domain='stock', published=False)
def tech_sync(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    result = np.where(pd.notna(ma20), (df['close'] > ma20).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(tech_sync=result)


@factor(name='ma_bull', category='pv', label='多头均线排列', domain='stock', published=False)
def ma_bull(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma5 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    result = np.where(ok & (ma5 > ma10) & (ma10 > ma20), 1, np.where(ok, 0, np.nan))
    return df[['stock_code', 'trade_date']].assign(ma_bull=result)


@factor(name='ma_bear', category='pv', label='空头均线排列', domain='stock', published=False)
def ma_bear(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma5 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    result = np.where(ok & (ma5 < ma10) & (ma10 < ma20), 1, np.where(ok, 0, np.nan))
    return df[['stock_code', 'trade_date']].assign(ma_bear=result)


@factor(name='break_cons', category='pv', label='突破整理平台', domain='stock', published=False)
def break_cons(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    high20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).max())
    result = np.where(pd.notna(high20), (df['close'] == high20).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(break_cons=result)
