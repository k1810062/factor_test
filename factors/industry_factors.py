"""行业日度因子函数库。每个因子加 @factor 装饰器，通过 api 取数。

返回带 key 列（industry_code, trade_date）+ 因子列的 DataFrame。
"""

from math import ceil

def _mapping(api):
    """取行业映射（stock_code → industry_code）。"""
    return api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code'])

def _swi_idx(api):
    """取行业指数日线。"""
    return api.table('industry_daily', columns=['industry_code', 'trade_date', 'close']).rename(
        columns={'close': 'idx_close'})

# ─── 8 个简单均值因子 ───

@factor(name='up_ratio', category='pv', label='上涨家数占比', domain='industry')
def up_ratio(api):
    return api.query("""
        SELECT s.industry_code, f.trade_date,
               AVG(f.up_stock) as up_ratio
        FROM stock_features f
        JOIN stock_industry s ON f.stock_code = s.stock_code AND f.trade_date = s.trade_date
        GROUP BY s.industry_code, f.trade_date
    """)

@factor(name='strong_ratio', category='pv', label='强势股涨幅占比', domain='industry')
def strong_ratio(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'strong_stock'])
    return fac.groupby(['industry_code', 'trade_date'])['strong_stock'].mean().reset_index(name='strong_ratio')

@factor(name='vol_ratio', category='pv', label='强势成交量占比', domain='industry')
def vol_ratio(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'strong_volume'])
    return fac.groupby(['industry_code', 'trade_date'])['strong_volume'].mean().reset_index(name='vol_ratio')

@factor(name='ma8_pos_avg', category='pv', label='8日均线多头占比', domain='industry')
def ma8_pos_avg(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'ma8_pos'])
    return fac.groupby(['industry_code', 'trade_date'])['ma8_pos'].mean().reset_index(name='ma8_pos_avg')

@factor(name='tech_sync_rt', category='pv', label='技术指标同步率', domain='industry')
def tech_sync_rt(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'tech_sync'])
    return fac.groupby(['industry_code', 'trade_date'])['tech_sync'].mean().reset_index(name='tech_sync_rt')

@factor(name='break_cons_rt', category='pv', label='突破整理形态占比', domain='industry')
def break_cons_rt(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'break_cons'])
    return fac.groupby(['industry_code', 'trade_date'])['break_cons'].mean().reset_index(name='break_cons_rt')

@factor(name='ma_bull', category='pv', label='多头均线占比', domain='industry')
def ma_bull(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'ma_bull'])
    return fac.groupby(['industry_code', 'trade_date'])['ma_bull'].mean().reset_index()

@factor(name='ma_bear', category='pv', label='空头均线占比', domain='industry')
def ma_bear(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'ma_bear'])
    return fac.groupby(['industry_code', 'trade_date'])['ma_bear'].mean().reset_index()

@factor(name='ma5_ratio', category='pv', label='MA5上方占比', domain='industry')
def ma5_ratio(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
    mapping = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code'])
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner')
    stock = stock.sort_values(['stock_code', 'trade_date'])
    ma5 = stock.groupby('stock_code')['close'].transform(lambda x: x.rolling(5).mean())
    stock['above_ma5'] = (stock['close'] > ma5).astype(int)
    return stock.groupby(['industry_code', 'trade_date'])['above_ma5'].mean().reset_index(name='ma5_ratio')

# ─── 10 个复杂因子（读原始数据） ───

@factor(name='strong_fund_ratio', category='fund', label='强势股资金占比', domain='industry')
def strong_fund_ratio(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'amount'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner')

    def _fund_ratio(g):
        cnt = max(ceil(len(g) * 0.1), 1)
        return g.nlargest(cnt, 'amount')['amount'].sum() / g['amount'].sum()

    return stock.groupby(['industry_code', 'trade_date'], group_keys=False).apply(
        _fund_ratio, include_groups=False).reset_index(name='strong_fund_ratio')

@factor(name='turn_pctl', category='ind', label='换手率分位数', domain='industry')
def turn_pctl(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'turn', 'mv'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['turn', 'mv'])
    ind_turn = stock.groupby(['industry_code', 'trade_date']).apply(
        lambda g: np.average(g['turn'], weights=g['mv']), include_groups=False
    ).reset_index(name='ind_turn').sort_values(['industry_code', 'trade_date']).reset_index(drop=True)

    def _pctl_250(s):
        if len(s) < 20:
            return np.nan
        return (s.iloc[:-1] < s.iloc[-1]).sum() / (len(s) - 1)

    ind_turn['turn_pctl'] = ind_turn.groupby('industry_code')['ind_turn'].transform(
        lambda x: x.rolling(250, min_periods=20).apply(_pctl_250))
    return ind_turn[['industry_code', 'trade_date', 'turn_pctl']]

@factor(name='diverge_5d', category='fund', label='主力资金背离度', domain='industry')
def diverge_5d(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'inflow_rate', 'mv'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['inflow_rate', 'mv'])
    ind_inflow = stock.groupby(['industry_code', 'trade_date']).apply(
        lambda g: np.average(g['inflow_rate'], weights=g['mv']), include_groups=False
    ).reset_index(name='ind_inflow').sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    ind_inflow['inflow_5d'] = ind_inflow.groupby('industry_code')['ind_inflow'].transform(lambda x: x.rolling(5).sum())

    swidx = _swi_idx(api).sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    swidx['ret_5d'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(5) - 1)
    diverge = ind_inflow.merge(swidx[['industry_code', 'trade_date', 'ret_5d']],
                                on=['industry_code', 'trade_date'], how='left')
    diverge['diverge_5d'] = diverge['inflow_5d'] - diverge['ret_5d']
    return diverge[['industry_code', 'trade_date', 'diverge_5d']]

@factor(name='ret_divg', category='ind', label='涨幅分化度', domain='industry')
def ret_divg(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'close', 'mv'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['close', 'mv'])
    stock = stock.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
    stock['stock_ret'] = stock.groupby('stock_code')['close'].transform(lambda x: x / x.shift(1) - 1)
    top3_ret = stock.groupby(['industry_code', 'trade_date']).apply(
        lambda g: g.nlargest(3, 'mv')['stock_ret'].mean(), include_groups=False
    ).reset_index(name='top3_ret')

    swidx = _swi_idx(api).sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    swidx['idx_ret'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(1) - 1)
    ret = top3_ret.merge(swidx[['industry_code', 'trade_date', 'idx_ret']],
                          on=['industry_code', 'trade_date'], how='left')
    ret['ret_divg'] = ret['top3_ret'] - ret['idx_ret']
    return ret[['industry_code', 'trade_date', 'ret_divg']]

@factor(name='amt_divg', category='fund', label='成交占比乖离率', domain='industry')
def amt_divg(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'amount'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['amount'])
    total_amt = stock.groupby('trade_date')['amount'].sum().reset_index(name='total_amt')
    ind_amt = stock.groupby(['industry_code', 'trade_date'])['amount'].sum().reset_index(name='ind_amt')
    amt = ind_amt.merge(total_amt, on='trade_date', how='left')
    amt['amt_ratio'] = amt['ind_amt'] / amt['total_amt']
    amt = amt.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    amt['amt_ma20'] = amt.groupby('industry_code')['amt_ratio'].transform(lambda x: x.rolling(20).mean())
    amt['amt_divg'] = amt['amt_ratio'] / amt['amt_ma20'] - 1
    return amt[['industry_code', 'trade_date', 'amt_divg']]

@factor(name='margin_dir', category='fund', label='融资盘方向', domain='industry')
def margin_dir(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'borrow_buy', 'borrow_repay'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['borrow_buy', 'borrow_repay'])
    stock['net_margin'] = stock['borrow_buy'] - stock['borrow_repay']
    ind = stock.groupby(['industry_code', 'trade_date'])['net_margin'].sum().reset_index()
    ind = ind.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    ind['chg_rt'] = ind.groupby('industry_code')['net_margin'].transform(lambda x: x / x.shift(1) - 1)
    ind['margin_dir'] = ind.groupby('industry_code')['chg_rt'].transform(lambda x: x.rolling(3).mean())
    return ind[['industry_code', 'trade_date', 'margin_dir']]

@factor(name='margin_sum5', category='fund', label='融资净买入5日滚动', domain='industry')
def margin_sum5(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'borrow_buy', 'borrow_repay'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['borrow_buy', 'borrow_repay'])
    stock['net_margin'] = stock['borrow_buy'] - stock['borrow_repay']
    ind = stock.groupby(['industry_code', 'trade_date'])['net_margin'].sum().reset_index()
    ind = ind.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    ind['margin_sum5'] = ind.groupby('industry_code')['net_margin'].transform(lambda x: x.rolling(5).sum())
    return ind[['industry_code', 'trade_date', 'margin_sum5']]

@factor(name='pb_disp', category='ind', label='估值离散度', domain='industry')
def pb_disp(api):
    stock = api.table('stock_daily', columns=['stock_code', 'trade_date', 'mv', 'net_asset_value'])
    mapping = _mapping(api)
    stock = stock.merge(mapping, on=['stock_code', 'trade_date'], how='inner').dropna(subset=['mv', 'net_asset_value'])
    stock = stock.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
    ind_pb = stock.groupby(['industry_code', 'trade_date']).apply(
        lambda g: g['mv'].sum() / g['net_asset_value'].sum(), include_groups=False
    ).reset_index(name='ind_pb').sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    ind_pb['pb_pctl'] = ind_pb.groupby('industry_code')['ind_pb'].transform(
        lambda x: x.rolling(1250, min_periods=250).apply(
            lambda s: (s <= s.iloc[-1]).sum() / len(s) if len(s) >= 20 else np.nan))
    ind_pb['pb_disp'] = ind_pb.groupby('industry_code')['pb_pctl'].transform(lambda x: x.rolling(20).std())
    return ind_pb[['industry_code', 'trade_date', 'pb_disp']]

@factor(name='etf_inflow_st', category='fund', label='行业ETF净流入5日平滑', domain='industry')
def etf_inflow_st(api):
    df = api.table('etf_daily')
    df['trade_date'] = df['trade_date'].astype(str)
    ind = df.groupby(['industry_code', 'trade_date'])['净流入金额（万元）'].sum().reset_index()
    ind = ind.rename(columns={'industry_code': 'industry_code', 'trade_date': 'trade_date', '净流入金额（万元）': 'inflow_amt'})
    ind = ind.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
    ind['etf_inflow_st'] = ind.groupby('industry_code')['inflow_amt'].transform(lambda x: x.rolling(5).mean())
    return ind[['industry_code', 'trade_date', 'etf_inflow_st']]

@factor(name='mom_12m', category='ind', label='动量因子', domain='industry')
def mom_12m(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (LAG(close, 21) OVER w / LAG(close, 252) OVER w - 1) as mom_12m
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

# ─── 新增草稿因子 ───

@factor(name='pct_5d', category='pv', label='5日涨幅', domain='industry')
def pct_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / LAG(close, 5) OVER w - 1) as pct_5d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

# ─── 新增草稿因子 ───
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / lag(close, 5) OVER w - 1) as ret_5d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

@factor(name='ma_5d', category='pv', label='5日涨幅', domain='industry')
def ma_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / LAG(close, 5) OVER w - 1) as ma_5d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

@factor(name='ma_10d', category='pv', label='10日涨幅', domain='industry')
def ma_10d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / LAG(close, 10) OVER w - 1) as ma_10d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

# ─── 新增草稿因子 ───
@factor(name='ma_5d', category='pv', label='5日涨幅', domain='industry')
def ma_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / LAG(close, 5) OVER w - 1) as ma_5d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

@factor(name='ma_10d', category='pv', label='10日涨幅', domain='industry')
def ma_10d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / LAG(close, 10) OVER w - 1) as ma_10d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)

# ─── 新增草稿因子 ───
@factor(name='bull_bear_spread', category='ind', label='多空均线差', domain='industry')
def bull_bear_spread(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (ma_bull - ma_bear) as bull_bear_spread
        FROM industry_daily
    """)
    
@factor(name='roe_improve', category='monthly', label='盈利景气改善', domain='industry_monthly')
def roe_improve(api):
    df = api.table('industry_monthly', columns=['industry_code', 'ym', 'roe_pctl'])
    df = df.sort_values(['industry_code', 'ym'])
    df['roe_improve'] = df.groupby('industry_code')['roe_pctl'].diff(1)
    return df[['industry_code', 'ym', 'roe_improve']]

# ─── 新增草稿因子 ───
@factor(name='bull_bear_spread', category='ind', label='多空均线差', domain='industry')
def bull_bear_spread(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (ma_bull - ma_bear) as bull_bear_spread
        FROM industry_daily
    """)
    
@factor(name='roe_improve', category='monthly', label='盈利景气改善', domain='industry_monthly')
def roe_improve(api):
    df = api.table('industry_monthly', columns=['industry_code', 'ym', 'roe_pctl'])
    df = df.sort_values(['industry_code', 'ym'])
    df['roe_improve'] = df.groupby('industry_code')['roe_pctl'].diff(1)
    return df[['industry_code', 'ym', 'roe_improve']]

# ─── 新增草稿因子 ───
@factor(name='test_idx_hl', category='ind', label='测试高低差', domain='industry')
def test_idx_hl(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close - open) / (open + 1e-10) as test_idx_hl
        FROM industry_daily
    """)

# ─── 新增因子 ───
@factor(name='test_ma8_avg', category='pv', label='测试20日线上占比', domain='industry')
def test_ma8_avg(api):
    fac = api.table('stock_features', columns=['stock_code', 'trade_date', 'industry_code', 'test_ma8_pos'])
    return fac.groupby(['industry_code', 'trade_date'])['test_ma8_pos'].mean().reset_index(name='test_ma8_avg')
