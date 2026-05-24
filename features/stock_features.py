"""特征（中间量）函数库。每个特征加 @feature 装饰器，只计算不分析。
"""

def _fib_ma(df, n):
    return df.groupby('stock_code')['close'].transform(lambda x: x.rolling(n).mean())

@feature(name='up_stock', domain='stock')
def up_stock(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    close_diff = df.groupby('stock_code')['close'].diff()
    result = np.where(close_diff.notna(), (close_diff > 0).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(up_stock=result)

@feature(name='strong_stock', domain='stock')
def strong_stock(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma60 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(60).mean())
    result = np.where(pd.notna(ma60), (df['close'] > ma60).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(strong_stock=result)

@feature(name='strong_volume', domain='stock')
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

@feature(name='ma8_pos', domain='stock')
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

@feature(name='tech_sync', domain='stock')
def tech_sync(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    result = np.where(pd.notna(ma20), (df['close'] > ma20).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(tech_sync=result)

@feature(name='ma_bull', domain='stock')
def ma_bull(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma5 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    result = np.where(ok & (ma5 > ma10) & (ma10 > ma20), 1, np.where(ok, 0, np.nan))
    return df[['stock_code', 'trade_date']].assign(ma_bull=result)

@feature(name='ma_bear', domain='stock')
def ma_bear(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    ma5 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(5).mean())
    ma10 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(10).mean())
    ma20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).mean())
    ok = pd.notna(ma5)
    result = np.where(ok & (ma5 < ma10) & (ma10 < ma20), 1, np.where(ok, 0, np.nan))
    return df[['stock_code', 'trade_date']].assign(ma_bear=result)

@feature(name='break_cons', domain='stock')
def break_cons(api):
    df = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    high20 = df.groupby('stock_code')['close'].transform(lambda x: x.rolling(20).max())
    result = np.where(pd.notna(high20), (df['close'] == high20).astype(int), np.nan)
    return df[['stock_code', 'trade_date']].assign(break_cons=result)
