"""个股因子函数库。每个因子一个独立函数，输入 df，返回该因子列（Series）。"""
import pandas as pd
import numpy as np


def up_stock(df):
    """当日是否上涨。"""
    close_diff = df.groupby('STOCK_CODE')['CLOSE'].diff()
    return np.where(close_diff.notna(), (close_diff > 0).astype(int), np.nan)


def ma60(df):
    """60 日均线（中间变量）。"""
    return df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(60).mean())


def strong_stock(df):
    """收盘价 > 60日均线。"""
    ma = ma60(df)
    return np.where(pd.notna(ma), (df['CLOSE'] > ma).astype(int), np.nan)


def _fib_ma(df, n):
    """n 日均线（通用）。"""
    return df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(n).mean())


def ma8_pos(df):
    """8 条 Fibonacci 均线位置。"""
    fibs = [8, 13, 21, 34, 55, 89, 144, 233]
    ma_cols = []
    for n in fibs:
        col = f'_ma{n}'
        df[col] = _fib_ma(df, n)
        ma_cols.append(col)
    vals = df[['CLOSE'] + ma_cols].values
    ranks = vals.argsort(axis=1).argsort(axis=1) + 1
    close_rank = ranks[:, 0]
    result = np.select([close_rank <= 3, close_rank <= 6], [-1, 0], default=1)
    has_all = pd.DataFrame({c: df[c].notna() for c in ma_cols}).all(axis=1).values
    result = np.where(has_all, result, np.nan).astype(float)
    for c in ma_cols:
        df.drop(columns=[c], inplace=True)
    return result


def tech_sync(df):
    """收盘价 > 20日均线。"""
    ma20 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(20).mean())
    return np.where(pd.notna(ma20), (df['CLOSE'] > ma20).astype(int), np.nan)


def ma_bull(df):
    """多头均线：MA5 > MA10 > MA20。"""
    ma5 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    return np.where(ok & (ma5 > ma10) & (ma10 > ma20), 1, np.where(ok, 0, np.nan))


def ma_bear(df):
    """空头均线：MA5 < MA10 < MA20。"""
    ma5 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    return np.where(ok & (ma5 < ma10) & (ma10 < ma20), 1, np.where(ok, 0, np.nan))


def vol_trim_mean(df):
    """20 日成交量去掉最高最低后的均值（中间变量）。"""
    g = df.groupby('STOCK_CODE')['VOL']
    s20 = g.transform(lambda x: x.rolling(20).sum())
    min20 = g.transform(lambda x: x.rolling(20).min())
    max20 = g.transform(lambda x: x.rolling(20).max())
    cnt20 = g.transform(lambda x: x.rolling(20).count())
    return np.where(cnt20 >= 3, (s20 - min20 - max20) / (cnt20 - 2), np.nan)


def strong_volume(df):
    """成交量 > 过去20日去极值均值×1.06。"""
    trim = vol_trim_mean(df)
    return np.where(pd.notna(trim), (df['VOL'] / trim > 1.06).astype(int), np.nan)


def break_cons(df):
    """收盘价为过去20日最高。"""
    high20 = df.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(20).max())
    return np.where(pd.notna(high20), (df['CLOSE'] == high20).astype(int), np.nan)


# 因子名 → 所需 stock_base 列（用于按需读取）
FACTOR_COLUMNS = {
    'up_stock': ['CLOSE'],
    'strong_stock': ['CLOSE'],
    'strong_volume': ['VOL'],
    'ma8_pos': ['CLOSE'],
    'tech_sync': ['CLOSE'],
    'break_cons': ['CLOSE'],
    'ma_bull': ['CLOSE'],
    'ma_bear': ['CLOSE'],
}

# 因子名 → 函数映射
STOCK_FACTORS = {
    'up_stock': up_stock,
    'strong_stock': strong_stock,
    'strong_volume': strong_volume,
    'ma8_pos': ma8_pos,
    'tech_sync': tech_sync,
    'break_cons': break_cons,
    'ma_bull': ma_bull,
    'ma_bear': ma_bear,
}
