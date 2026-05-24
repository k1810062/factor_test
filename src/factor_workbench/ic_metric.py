"""Rank IC 分析 + 十分组累计收益。@metric 装饰器注册。"""

import warnings, json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
from scipy.stats import spearmanr
from .registry import metric


def _nw_std(x, max_lag):
    """Newey-West 调整标准差，用于重叠期 IC 的标准差修正。"""
    T = len(x)
    mu = np.mean(x)
    gamma_0 = np.var(x, ddof=0)
    nw_var = gamma_0
    for k in range(1, min(max_lag + 1, T - 2)):
        cov = np.mean((x[k:] - mu) * (x[:-k] - mu))
        nw_var += 2 * (1 - k / (max_lag + 1)) * cov
    return np.sqrt(max(nw_var, 1e-10))


def _calc_nw_icir(ic_series, horizon, ann_factor):
    """年化 + Newey-West 调整的 ICIR。返回 (mean, nw_std, ann_icir)。"""
    s = ic_series.dropna()
    if len(s) < 10:
        return np.nan, np.nan, np.nan
    mu = np.mean(s)
    std = _nw_std(s.values, max(0, horizon - 1))
    icir = mu / std * ann_factor if std > 0 else np.nan
    return mu, std, icir


warnings.filterwarnings('ignore', message='An input array is constant')

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False


def _calc_rank_ic(df, factor_col, ret_col):
    dates, ics = [], []
    for date, grp in df.groupby('trade_date'):
        vals = grp[[factor_col, ret_col]].dropna()
        if len(vals) < 10:
            continue
        ic, _ = spearmanr(vals[factor_col], vals[ret_col])
        dates.append(date); ics.append(ic)
    return pd.Series(ics, index=pd.to_datetime(dates, format='%Y%m%d'))


def _calc_decile_rets(df, col):
    dates, rets = [], []
    for date, grp in df.groupby('trade_date'):
        grp = grp.dropna(subset=[col, 'ret_T1'])
        if len(grp) < 15:
            continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), 10, labels=False)
        rets.append(grp.groupby('decile')['ret_T1'].mean().values)
        dates.append(date)
    return pd.DataFrame(rets, index=pd.to_datetime(dates, format='%Y%m%d'))


def _plot_cumulative_ic(ic_dict, label, path):
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        ax.plot(ic_s.index, ic_s.cumsum().values, lw=1.5, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('累计 Rank IC'); ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def _plot_ic_ts(ic_dict, label, path):
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        monthly = ic_s.resample('ME').mean()
        ax.plot(ic_s.index, ic_s.values, alpha=0.15, lw=0.5, color=c)
        ax.plot(monthly.index, monthly.values, lw=1.8, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('Rank IC'); ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def _plot_ic_comp(ic_dict, label, path):
    hs = sorted(ic_dict.keys())
    means, stds, icirs = [], [], []
    for h in hs:
        mu, std, _ = _calc_nw_icir(ic_dict[h], h, 1)
        means.append(mu); stds.append(std); icirs.append(mu / std if std > 0 else np.nan)
    x = np.arange(len(hs)); w = 0.28
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    a1.bar(x - w, means, w, label='IC 均值', color='steelblue')
    a1.bar(x, stds, w, label='IC 标准差', color='lightcoral')
    a1.set_title(f'{label} — IC 汇总'); a1.legend(fontsize=9); a1.axhline(0, ls=':', lw=0.6)
    a2.bar(x, icirs, w * 1.5, color='darkgreen', label='ICIR')
    a2.set_xticks(x); a2.set_xticklabels([f'T+{h}' for h in hs]); a2.legend(fontsize=9); a2.axhline(0, ls=':', lw=0.6)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def _plot_ret_decile(decile_rets, label, path):
    cum = (1 + decile_rets).cumprod() - 1
    fig, ax = plt.subplots(figsize=(12, 4.5))
    cmap = plt.cm.RdYlBu_r
    for i in range(10):
        ax.plot(cum.index, cum[i], lw=1.3, color=cmap(i / 9), label=f'D{i+1}')
    ax.axhline(0, color='gray', ls='--', lw=0.6); ax.set_ylabel('累计收益')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
    ax.legend(fontsize=7, ncol=5); ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def _plot_decile_bar(decile_rets, label, path):
    means = decile_rets.mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [plt.cm.RdYlBu_r(i / 9) for i in range(10)]
    ax.bar(range(10), means.values, color=colors, width=0.6, edgecolor='white')
    ax.axhline(0, color='gray', ls=':', lw=0.6)
    ax.set_xticks(range(10)); ax.set_xticklabels([f'D{i+1}' for i in range(10)])
    ax.set_ylabel('日均收益率（%）'); ax.set_title(f'{label} — 十分组平均收益')
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def _plot_long_short(decile_rets, label, path):
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


@metric(name='ic', label='Rank IC分析')
def ic_metric(df, col, cn_label, cat, base_path):
    ic_dir = f'{base_path}/ic'; ret_dir = f'{base_path}/ret'
    os.makedirs(ic_dir, exist_ok=True); os.makedirs(ret_dir, exist_ok=True)

    horizons = sorted(int(h.split('_T')[1]) for h in df.columns if h.startswith('ret_T'))
    if not horizons:
        print(f'  [{col}] 无 ret_T 列，跳过')
        return

    ic_dict = {}
    for h in horizons:
        ic_dict[h] = _calc_rank_ic(df, col, f'ret_T{h}')

    # 年化：日频 √252，月频 √12
    ann_factor = np.sqrt(12) if '/monthly/' in base_path else np.sqrt(252)

    # T+1
    mu, std, icir = _calc_nw_icir(ic_dict[1], 1, ann_factor)
    t_stat = mu / (std / np.sqrt(len(ic_dict[1].dropna()))) if std > 0 else np.nan

    with open(f'{ic_dir}/{col}_ic.json', 'w') as f:
        horizons_data = []
        for h in horizons:
            hm, hs, hir = _calc_nw_icir(ic_dict[h], h, ann_factor)
            ht = hm / (hs / np.sqrt(len(ic_dict[h].dropna()))) if hs > 0 else 0
            horizons_data.append({
                'h': h, 'ic_mean': round(hm, 6), 'ic_std': round(hs, 6),
                'icir': round(hir, 4), 't_stat': round(ht, 4),
            })
        json.dump({
            'name': col, 'label': cn_label,
            'n_months': len(ic_dict[1].dropna()),
            'ic_mean': round(mu, 6), 'ic_std': round(std, 6),
            'icir': round(icir, 4), 't_stat': round(t_stat, 4),
            'horizons': horizons_data,
        }, f, indent=2, ensure_ascii=False)

    _plot_cumulative_ic(ic_dict, cn_label, f'{ic_dir}/ic_cum.png')
    _plot_ic_ts(ic_dict, cn_label, f'{ic_dir}/ic_ts.png')
    _plot_ic_comp(ic_dict, cn_label, f'{ic_dir}/ic_comp.png')

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

    ic_df = pd.DataFrame({f'T+{h}': ic_dict[h] for h in horizons}).reset_index()
    ic_df.columns = ['trade_date'] + [f'T+{h}' for h in horizons]
    ic_df['trade_date'] = ic_df['trade_date'].dt.strftime('%Y%m%d')
    ic_df.to_parquet(f'{ic_dir}/{col}_ic.parquet', index=False)

    decile_rets = _calc_decile_rets(df, col)
    decile_rets.to_parquet(f'{ret_dir}/{col}_decile_rets.parquet', index=True)
    _plot_ret_decile(decile_rets, cn_label, f'{ret_dir}/ret_decile.png')
    _plot_decile_bar(decile_rets, cn_label, f'{ret_dir}/ret_decile_bar.png')
    _plot_long_short(decile_rets, cn_label, f'{ret_dir}/ret_long_short.png')
    ret_mean = decile_rets.mean()
    with open(f'{ret_dir}/{col}_ret.json', 'w') as f:
        json.dump({
            'ret_D1': round(float(ret_mean[0]), 8),
            'ret_D10': round(float(ret_mean[9]), 8),
            'ret_spread': round(float(ret_mean[9] - ret_mean[0]), 8),
        }, f, indent=2, ensure_ascii=False)
    print(f'  [{col}] 完成')
