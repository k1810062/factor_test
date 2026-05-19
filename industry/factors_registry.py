"""行业级因子函数库。每个因子一个独立函数，返回 (industry_code, TRADE_DATE, 因子列) 的 DataFrame。"""
import pandas as pd
import numpy as np
from math import ceil

out_dir = 'output/data_processed'
data_dir = 'data'


def base_ratios(fac):
    """基础行业均值（up/ strong/ vol/ ma8/ tech_sync/ break_cons）。"""
    return fac.groupby(['industry', 'TRADE_DATE'], as_index=False)[
        ['up_stock', 'strong_stock', 'strong_volume', 'ma8_pos', 'tech_sync', 'break_cons']
    ].mean().rename(columns={
        'up_stock': 'up_ratio', 'strong_stock': 'strong_ratio',
        'strong_volume': 'vol_ratio', 'ma8_pos': 'ma8_pos_avg',
        'tech_sync': 'tech_sync_rt', 'break_cons': 'break_cons_rt',
    })


def strong_fund_ratio(mapping):
    """强势资金占比（成交额前10%的占比）。"""
    _fund_orig = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                                  columns=['STOCK_CODE', 'TRADE_DATE', 'AMOUNT'])
    _fund_orig = _fund_orig.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    def _fund_ratio(g):
        cnt = max(ceil(len(g) * 0.1), 1)
        return g.nlargest(cnt, 'AMOUNT')['AMOUNT'].sum() / g['AMOUNT'].sum()
    return _fund_orig.groupby(['industry_code', 'TRADE_DATE'], group_keys=False).apply(
        _fund_ratio, include_groups=False).reset_index(name='strong_fund_ratio')


def turn_pctl(mapping):
    """换手率分位数（行业MV加权换手率的250天分位）。"""
    tdata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'TURN', 'MV'])
    tdata = tdata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['TURN', 'MV'])
    ind_turn = tdata.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: np.average(g['TURN'], weights=g['MV']), include_groups=False
    ).reset_index(name='ind_turn').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    def _pctl_250(s):
        if len(s) < 20: return np.nan
        return (s.iloc[:-1] < s.iloc[-1]).sum() / (len(s) - 1)
    ind_turn['turn_pctl'] = ind_turn.groupby('industry_code')['ind_turn'].transform(
        lambda x: x.rolling(250, min_periods=20).apply(_pctl_250))
    return ind_turn[['industry_code', 'TRADE_DATE', 'turn_pctl']]


def diverge_5d(mapping):
    """主力资金背离度（5日累计净流入 - 5日指数涨跌）。"""
    ndata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'INFLOW_RATE', 'MV'])
    ndata = ndata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['INFLOW_RATE', 'MV'])
    ind_inflow = ndata.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: np.average(g['INFLOW_RATE'], weights=g['MV']), include_groups=False
    ).reset_index(name='ind_inflow').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_inflow['inflow_5d'] = ind_inflow.groupby('industry_code')['ind_inflow'].transform(
        lambda x: x.rolling(5).sum())
    swidx = (pd.read_parquet(f'{data_dir}/SWI_daily.parquet',
                              columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
             .rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
             .sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True))
    swidx['ret_5d'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(5) - 1)
    diverge = ind_inflow.merge(swidx[['industry_code', 'TRADE_DATE', 'ret_5d']],
                                on=['industry_code', 'TRADE_DATE'], how='left')
    diverge['diverge_5d'] = diverge['inflow_5d'] - diverge['ret_5d']
    return diverge[['industry_code', 'TRADE_DATE', 'diverge_5d']]


def ret_divg(mapping):
    """涨幅分化度（行业前3大市值股票平均涨幅 - 板块指数涨幅）。"""
    rdata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE', 'MV'])
    rdata = rdata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['CLOSE', 'MV'])
    rdata = rdata.sort_values(['STOCK_CODE', 'TRADE_DATE']).reset_index(drop=True)
    rdata['stock_ret'] = rdata.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x / x.shift(1) - 1)
    top3_ret = rdata.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: g.nlargest(3, 'MV')['stock_ret'].mean(), include_groups=False
    ).reset_index(name='top3_ret')
    swidx = (pd.read_parquet(f'{data_dir}/SWI_daily.parquet',
                              columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
             .rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
             .sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True))
    swidx['idx_ret'] = swidx.groupby('industry_code')['idx_close'].transform(lambda x: x / x.shift(1) - 1)
    ret = top3_ret.merge(swidx[['industry_code', 'TRADE_DATE', 'idx_ret']],
                          on=['industry_code', 'TRADE_DATE'], how='left')
    ret['ret_divg'] = ret['top3_ret'] - ret['idx_ret']
    return ret[['industry_code', 'TRADE_DATE', 'ret_divg']]


def amt_divg(mapping):
    """成交占比乖离率（板块成交额占比 / 20日均值 - 1）。"""
    adata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'AMOUNT'])
    adata = adata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['AMOUNT'])
    total_amt = adata.groupby('TRADE_DATE')['AMOUNT'].sum().reset_index(name='total_amt')
    ind_amt = adata.groupby(['industry_code', 'TRADE_DATE'])['AMOUNT'].sum().reset_index(name='ind_amt')
    amt = ind_amt.merge(total_amt, on='TRADE_DATE', how='left')
    amt['amt_ratio'] = amt['ind_amt'] / amt['total_amt']
    amt = amt.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    amt['amt_ma20'] = amt.groupby('industry_code')['amt_ratio'].transform(lambda x: x.rolling(20).mean())
    amt['amt_divg'] = amt['amt_ratio'] / amt['amt_ma20'] - 1
    return amt[['industry_code', 'TRADE_DATE', 'amt_divg']]


def margin_dir(mapping):
    """融资盘方向（融资净买入变化率3日移动平均）。"""
    mdata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'BORROW_BUY', 'BORROW_REPAY'])
    mdata = mdata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['BORROW_BUY', 'BORROW_REPAY'])
    mdata['net_margin'] = mdata['BORROW_BUY'] - mdata['BORROW_REPAY']
    ind_margin = mdata.groupby(['industry_code', 'TRADE_DATE'])['net_margin'].sum().reset_index()
    ind_margin = ind_margin.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_margin['chg_rt'] = ind_margin.groupby('industry_code')['net_margin'].transform(lambda x: x / x.shift(1) - 1)
    ind_margin['margin_dir'] = ind_margin.groupby('industry_code')['chg_rt'].transform(lambda x: x.rolling(3).mean())
    return ind_margin[['industry_code', 'TRADE_DATE', 'margin_dir']]


def margin_sum5(mapping):
    """区间融资净买入（5日滚动求和）。"""
    mdata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'BORROW_BUY', 'BORROW_REPAY'])
    mdata = mdata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['BORROW_BUY', 'BORROW_REPAY'])
    mdata['net_margin'] = mdata['BORROW_BUY'] - mdata['BORROW_REPAY']
    ind_margin = mdata.groupby(['industry_code', 'TRADE_DATE'])['net_margin'].sum().reset_index()
    ind_margin = ind_margin.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_margin['margin_sum5'] = ind_margin.groupby('industry_code')['net_margin'].transform(lambda x: x.rolling(5).sum())
    return ind_margin[['industry_code', 'TRADE_DATE', 'margin_sum5']]


def pb_disp(mapping):
    """估值离散度（行业PB的5年历史分位点的20日标准差）。"""
    pdata = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                             columns=['STOCK_CODE', 'TRADE_DATE', 'MV', 'NET_ASSET_VALUE'])
    pdata = pdata.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner').dropna(subset=['MV', 'NET_ASSET_VALUE'])
    pdata = pdata.sort_values(['STOCK_CODE', 'TRADE_DATE']).reset_index(drop=True)
    ind_pb = pdata.groupby(['industry_code', 'TRADE_DATE']).apply(
        lambda g: g['MV'].sum() / g['NET_ASSET_VALUE'].sum(), include_groups=False
    ).reset_index(name='ind_pb').sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind_pb['pb_pctl'] = ind_pb.groupby('industry_code')['ind_pb'].transform(
        lambda x: x.rolling(1250, min_periods=250).apply(
            lambda s: (s <= s.iloc[-1]).sum() / len(s) if len(s) >= 20 else np.nan))
    ind_pb['pb_disp'] = ind_pb.groupby('industry_code')['pb_pctl'].transform(lambda x: x.rolling(20).std())
    return ind_pb[['industry_code', 'TRADE_DATE', 'pb_disp']]


def etf_inflow_st(mapping):
    """行业ETF净流入（静态映射，5日平滑）。"""
    df = pd.read_parquet(f'{data_dir}/etf_daily.parquet')
    df['TRADE_DT'] = df['TRADE_DT'].astype(str)
    ind = df.groupby(['INDUSTRY_CODE', 'TRADE_DT'])['净流入金额（万元）'].sum().reset_index()
    ind = ind.rename(columns={'INDUSTRY_CODE': 'industry_code', 'TRADE_DT': 'TRADE_DATE',
                               '净流入金额（万元）': 'inflow_amt'})
    ind = ind.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    ind['etf_inflow_st'] = ind.groupby('industry_code')['inflow_amt'].transform(lambda x: x.rolling(5).mean())
    return ind[['industry_code', 'TRADE_DATE', 'etf_inflow_st']]


# ---- 月度因子函数 ----
def base_monthly(out_dir):
    """月度基表：月末日期、行业、次月收益率。"""
    idx = (pd.read_parquet(f'{data_dir}/SWI_daily.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
            .rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
            .sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True))
    idx['ym'] = idx['TRADE_DATE'].str[:6]
    monthly_close = idx.groupby(['industry_code', 'ym']).tail(1).copy()
    monthly_close = monthly_close.sort_values(['industry_code', 'ym']).reset_index(drop=True)
    monthly_close['ret_T1'] = monthly_close.groupby('industry_code')['idx_close'].transform(
        lambda x: x.shift(-1) / x - 1)
    return monthly_close[['industry_code', 'ym', 'TRADE_DATE', 'ret_T1']]


def _rating_base():
    """读取股票评级数据（已含行业代码）。"""
    return pd.read_parquet(f'{data_dir}/stock_base.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code',
                                    'RATING_GRADE', 'VAL_MV'])


def upg_cnt_rt(**kw):
    """上调数量占比。"""
    src = _rating_base()
    src = src[src['RATING_GRADE'].notna()].copy()
    src['ym'] = src['TRADE_DATE'].str[:6]
    def agg(g):
        total = len(g)
        up_cnt = (g['RATING_GRADE'] == 1).sum()
        return up_cnt / total if total > 0 else 0
    return src.groupby(['industry_code', 'ym']).apply(agg, include_groups=False).reset_index(name='upg_cnt_rt')


def upg_mv_rt(**kw):
    """上调市值占比。"""
    src = _rating_base()
    src = src[src['RATING_GRADE'].notna()].copy()
    src['ym'] = src['TRADE_DATE'].str[:6]
    def agg(g):
        total_mv = g['VAL_MV'].sum()
        up_mv = g.loc[g['RATING_GRADE'] == 1, 'VAL_MV'].sum()
        return up_mv / total_mv if total_mv > 0 else 0
    return src.groupby(['industry_code', 'ym']).apply(agg, include_groups=False).reset_index(name='upg_mv_rt')


def roe_pctl(out_dir, **kw):
    """盈利景气度（MV加权ROE的36个月分位点）。"""
    src = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'ROE_TTM', 'MV'])
    ind_map = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                               columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code'])
    src = src.merge(ind_map, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    src = src.dropna(subset=['ROE_TTM', 'MV'])
    src['ym'] = src['TRADE_DATE'].str[:6]
    roe = src.groupby(['industry_code', 'ym']).apply(
        lambda g: np.average(g['ROE_TTM'], weights=g['MV']), include_groups=False
    ).reset_index(name='roe').sort_values(['industry_code', 'ym']).reset_index(drop=True)
    roe['roe_pctl'] = roe.groupby('industry_code')['roe'].transform(
        lambda x: x.rolling(36, min_periods=12).apply(
            lambda s: (s <= s.iloc[-1]).sum() / len(s)))
    return roe[['industry_code', 'ym', 'roe_pctl']]


def bull_ma_rt(mapping):
    """多头均线占比：成分股中 MA5 > MA10 > MA20 的比例。"""
    fac = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'ma_bull', 'industry_code'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['ma_bull'].mean().reset_index()


def bear_ma_rt(mapping):
    """空头均线占比：成分股中 MA5 < MA10 < MA20 的比例。"""
    fac = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'ma_bear', 'industry_code'])
    return fac.groupby(['industry_code', 'TRADE_DATE'])['ma_bear'].mean().reset_index()


def mom_12m(**kw):
    """动量因子（日度）：过去12月剔除近1月的行业指数累计收益。"""
    swidx = (pd.read_parquet(f'{data_dir}/SWI_daily.parquet',
                              columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
              .rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
              .sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True))
    swidx['mom_12m'] = swidx.groupby('industry_code')['idx_close'].transform(
        lambda x: x.shift(21) / x.shift(252) - 1)
    return swidx[['industry_code', 'TRADE_DATE', 'mom_12m']]


def mom_12m_m(out_dir, **kw):
    """动量因子（月度）：过去12月剔除近1月的行业指数累计收益。"""
    idx = (pd.read_parquet(f'{data_dir}/SWI_daily.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
            .rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
            .sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True))
    idx['ym'] = idx['TRADE_DATE'].str[:6]
    monthly_close = idx.groupby(['industry_code', 'ym']).tail(1).copy()
    monthly_close = monthly_close.sort_values(['industry_code', 'ym']).reset_index(drop=True)
    monthly_close['mom_12m_m'] = monthly_close.groupby('industry_code')['idx_close'].transform(
        lambda x: x.shift(1) / x.shift(12) - 1)
    return monthly_close[['industry_code', 'ym', 'mom_12m_m']]


# 个股基础因子的行业均值（通用函数）
def _stock_mean(col, out_name):
    def fn(**kw):
        fac = pd.read_parquet(f'{out_dir}/factor_stock.parquet',
                               columns=['STOCK_CODE', 'TRADE_DATE', col, 'industry_code'])
        return fac.groupby(['industry_code', 'TRADE_DATE'])[col].mean().reset_index(name=out_name)
    return fn


# 因子名 → 函数映射
FACTOR_FUNCTIONS = {
    'up_ratio': _stock_mean('up_stock', 'up_ratio'),
    'strong_ratio': _stock_mean('strong_stock', 'strong_ratio'),
    'vol_ratio': _stock_mean('strong_volume', 'vol_ratio'),
    'ma8_pos_avg': _stock_mean('ma8_pos', 'ma8_pos_avg'),
    'tech_sync_rt': _stock_mean('tech_sync', 'tech_sync_rt'),
    'break_cons_rt': _stock_mean('break_cons', 'break_cons_rt'),
    'ma_bull': _stock_mean('ma_bull', 'ma_bull'),
    'ma_bear': _stock_mean('ma_bear', 'ma_bear'),
    'strong_fund_ratio': lambda fac, mapping, **kw: strong_fund_ratio(mapping),
    'turn_pctl': lambda fac, mapping, **kw: turn_pctl(mapping),
    'diverge_5d': lambda fac, mapping, **kw: diverge_5d(mapping),
    'ret_divg': lambda fac, mapping, **kw: ret_divg(mapping),
    'amt_divg': lambda fac, mapping, **kw: amt_divg(mapping),
    'margin_dir': lambda fac, mapping, **kw: margin_dir(mapping),
    'margin_sum5': lambda fac, mapping, **kw: margin_sum5(mapping),
    'pb_disp': lambda fac, mapping, **kw: pb_disp(mapping),
    'etf_inflow_st': lambda fac, mapping, **kw: etf_inflow_st(mapping),
    # 月度因子
    'upg_cnt_rt': lambda fac, mapping, out_dir, **kw: upg_cnt_rt(out_dir=out_dir),
    'upg_mv_rt': lambda fac, mapping, out_dir, **kw: upg_mv_rt(out_dir=out_dir),
    'roe_pctl': lambda fac, mapping, out_dir, **kw: roe_pctl(out_dir=out_dir),
    'bull_ma_rt': lambda fac, mapping, **kw: bull_ma_rt(mapping),
    'bear_ma_rt': lambda fac, mapping, **kw: bear_ma_rt(mapping),
    'mom_12m': lambda fac, mapping, **kw: mom_12m(),
    'mom_12m_m': lambda fac, mapping, out_dir, **kw: mom_12m_m(out_dir=out_dir),
}
