"""Rank IC 分析 + 十分组累计收益。"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
from scipy.stats import spearmanr

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

data_dir = 'output/data_processed'
HORIZONS = [1, 5, 10, 22]


def add_forward_returns(df):
    g = df.groupby('industry_code')['idx_close']
    for h in HORIZONS:
        df[f'ret_t{h}'] = g.transform(lambda x: x.shift(-h) / x - 1)
    return df


def calc_rank_ic(df, factor_col, ret_col):
    dates, ics = [], []
    for date, grp in df.groupby('TRADE_DATE'):
        vals = grp[[factor_col, ret_col]].dropna()
        if len(vals) < 10: continue
        ic, _ = spearmanr(vals[factor_col], vals[ret_col])
        dates.append(date); ics.append(ic)
    return pd.Series(ics, index=pd.to_datetime(dates, format='%Y%m%d'))


def calc_decile_rets(df, col):
    dates, rets = [], []
    for date, grp in df.groupby('TRADE_DATE'):
        grp = grp.dropna(subset=[col, 'ret_t1'])
        if len(grp) < 15: continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), 10, labels=False)
        rets.append(grp.groupby('decile')['ret_t1'].mean().values)
        dates.append(date)
    return pd.DataFrame(rets, index=pd.to_datetime(dates, format='%Y%m%d'))


def plot_cumulative_ic(ic_dict, label, path):
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        ax.plot(ic_s.index, ic_s.cumsum().values, lw=1.5, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('累计 Rank IC'); ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_ic_ts(ic_dict, label, path):
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        monthly = ic_s.resample('ME').mean()
        ax.plot(ic_s.index, ic_s.values, alpha=0.15, lw=0.5, color=c)
        ax.plot(monthly.index, monthly.values, lw=1.8, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('Rank IC'); ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_ic_comp(ic_dict, label, path):
    hs = sorted(ic_dict.keys())
    means, stds, icirs = [], [], []
    for h in hs:
        s = ic_dict[h].dropna()
        means.append(s.mean()); stds.append(s.std())
        icirs.append(s.mean() / s.std() if s.std() > 0 else np.nan)
    x = np.arange(len(hs)); w = 0.28
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    a1.bar(x - w, means, w, label='IC 均值', color='steelblue')
    a1.bar(x, stds, w, label='IC 标准差', color='lightcoral')
    a1.set_title(f'{label} — IC 汇总'); a1.legend(fontsize=9); a1.axhline(0, ls=':', lw=0.6)
    a2.bar(x, icirs, w * 1.5, color='darkgreen', label='ICIR')
    a2.set_xticks(x); a2.set_xticklabels([f'T+{h}' for h in hs]); a2.legend(fontsize=9); a2.axhline(0, ls=':', lw=0.6)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_ret_decile(decile_rets, label, path):
    cum = (1 + decile_rets).cumprod() - 1
    fig, ax = plt.subplots(figsize=(12, 4.5))
    cmap = plt.cm.RdYlBu_r
    for i in range(10):
        ax.plot(cum.index, cum[i], lw=1.3, color=cmap(i / 9), label=f'D{i+1}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('累计收益')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
    ax.legend(fontsize=7, ncol=5); ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_decile_bar(decile_rets, label, path):
    means = decile_rets.mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [plt.cm.RdYlBu_r(i / 9) for i in range(10)]
    ax.bar(range(10), means.values, color=colors, width=0.6, edgecolor='white')
    ax.axhline(0, color='gray', ls=':', lw=0.6)
    ax.set_xticks(range(10)); ax.set_xticklabels([f'D{i+1}' for i in range(10)])
    ax.set_ylabel('日均收益率（%）'); ax.set_title(f'{label} — 十分组平均收益')
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def plot_long_short(decile_rets, label, path):
    lc = (1 + decile_rets[9]).cumprod() - 1
    sc = (1 + decile_rets[0]).cumprod() - 1
    spc = (1 + (decile_rets[9] - decile_rets[0])).cumprod() - 1
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(lc.index, lc.values, lw=1.5, color='crimson', label='多头(D10)')
    ax.plot(sc.index, sc.values, lw=1.5, color='steelblue', label='空头(D1)')
    ax.plot(spc.index, spc.values, lw=2, color='darkgreen', label='多空(D10-D1)')
    ax.axhline(0, color='gray', ls=':', lw=0.6); ax.set_ylabel('累计收益')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
    ax.legend(fontsize=9); ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def ic_ret_fn(df, col, cn_label, cat, base_path):
    ic_dir = f'{base_path}/ic'; ret_dir = f'{base_path}/ret'
    os.makedirs(ic_dir, exist_ok=True); os.makedirs(ret_dir, exist_ok=True)

    ic_dict = {}
    for h in HORIZONS:
        ic_dict[h] = calc_rank_ic(df, col, f'ret_t{h}')

    s = ic_dict[1].dropna()
    ic_mean, ic_std = s.mean(), s.std()
    icir = ic_mean / ic_std if ic_std > 0 else np.nan
    t_stat = ic_mean / (ic_std / np.sqrt(len(s))) if ic_std > 0 else np.nan

    with open(f'{ic_dir}/{col}_ic.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n样本数(月): {len(s)}\n')
        f.write(f'IC 均值: {ic_mean:.6f}\nIC 标准差: {ic_std:.6f}\nICIR: {icir:.4f}\nt 统计量: {t_stat:.4f}\n')
        f.write(f'\n{"Horizon":>8} {"IC均值":>10} {"IC标准差":>10} {"ICIR":>10} {"t统计量":>10}\n')
        for h in HORIZONS:
            s2 = ic_dict[h].dropna()
            m, std = s2.mean(), s2.std()
            ir = m / std if std > 0 else 0
            t = m / (std / np.sqrt(len(s2))) if std > 0 else 0
            f.write(f'{f"T+{h}":>8} {m:>10.6f} {std:>10.6f} {ir:>10.4f} {t:>10.4f}\n')

    plot_cumulative_ic(ic_dict, cn_label, f'{ic_dir}/ic_cum.png')
    plot_ic_ts(ic_dict, cn_label, f'{ic_dir}/ic_ts.png')
    plot_ic_comp(ic_dict, cn_label, f'{ic_dir}/ic_comp.png')

    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c, ax in zip(ic_dict.items(), colors, axes.flat):
        vals = ic_s.dropna()
        ax.hist(vals, bins=40, color=c, alpha=0.7, edgecolor='white')
        ax.axvline(0, color='gray', ls='--', lw=0.8)
        ax.axvline(vals.mean(), color='crimson', ls='-', lw=1.2, label=f'均值={vals.mean():.4f}')
        ax.set_title(f'T+{h}'); ax.set_xlabel('Rank IC'); ax.set_ylabel('频数'); ax.legend(fontsize=8)
    fig.suptitle(f'{cn_label} — IC 分布', fontsize=13)
    fig.tight_layout(); fig.savefig(f'{ic_dir}/ic_dist.png', dpi=150); plt.close(fig)

    ic_df = pd.DataFrame({f'T+{h}': ic_dict[h] for h in HORIZONS}).reset_index()
    ic_df.columns = ['TRADE_DATE'] + [f'T+{h}' for h in HORIZONS]
    ic_df['TRADE_DATE'] = ic_df['TRADE_DATE'].dt.strftime('%Y%m%d')
    ic_df.to_parquet(f'{ic_dir}/{col}_ic.parquet', index=False)

    decile_rets = calc_decile_rets(df, col)
    plot_ret_decile(decile_rets, cn_label, f'{ret_dir}/ret_decile.png')
    plot_decile_bar(decile_rets, cn_label, f'{ret_dir}/ret_decile_bar.png')
    plot_long_short(decile_rets, cn_label, f'{ret_dir}/ret_long_short.png')
    ret_mean = decile_rets.mean()
    with open(f'{ret_dir}/{col}_ret.txt', 'w') as f:
        f.write(f'ret_D1={ret_mean[0]:.8f}\nret_D10={ret_mean[9]:.8f}\n'
                f'ret_spread={ret_mean[9] - ret_mean[0]:.8f}\n')
    print(f'  [{col}] 完成')


def main():
    df = pd.read_parquet(f'{data_dir}/industry_daily_ratio.parquet')
    idx = pd.read_parquet('data/SWI_daily.parquet',
                          columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
    idx = idx.rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
    df = df.merge(idx, on=['industry_code', 'TRADE_DATE'], how='inner')
    df = df.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    df = add_forward_returns(df)

    from analysis_base import run_analysis
    run_analysis(df, ic_ret_fn, 'industry', check_subdir='ic')


if __name__ == '__main__':
    main()
