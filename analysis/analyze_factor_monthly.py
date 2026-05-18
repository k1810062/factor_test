"""月度因子分析。"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
from scipy.stats import spearmanr, kurtosis

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

data_dir = 'output/data_processed'
analysis_dir = 'output/factor_analysis'


def calc_rank_ic(df, factor_col):
    dates, ics = [], []
    for date, grp in df.groupby('TRADE_DATE'):
        vals = grp[[factor_col, 'next_ret']].dropna()
        if len(vals) < 10: continue
        ic, _ = spearmanr(vals[factor_col], vals['next_ret'])
        dates.append(date); ics.append(ic)
    return pd.Series(ics, index=pd.to_datetime(dates, format='%Y%m%d'))


def calc_decile_rets(df, col):
    dates, rets = [], []
    for date, grp in df.groupby('TRADE_DATE'):
        grp = grp.dropna(subset=[col, 'next_ret'])
        if len(grp) < 15: continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), 10, labels=False)
        rets.append(grp.groupby('decile')['next_ret'].mean().values)
        dates.append(date)
    return pd.DataFrame(rets, index=pd.to_datetime(dates, format='%Y%m%d'))


def plot_kurtosis_hist(series, label, save_path):
    s = series.dropna()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(s, bins=30, color='steelblue', density=True, alpha=0.7, edgecolor='white')
    mu, std = s.mean(), s.std()
    x = np.linspace(s.min(), s.max(), 200)
    ax.plot(x, 1 / (std * np.sqrt(2 * np.pi)) * np.exp(-(x - mu)**2 / (2 * std**2)), 'r--', lw=1.5, label='正态分布')
    ax.axvline(mu, color='crimson', ls='-', lw=1, label=f'均值={mu:.4f}')
    ax.set_xlabel('因子值'); ax.set_ylabel('密度'); ax.set_title(f'{label} — 分布 vs 正态'); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(save_path, dpi=150); plt.close(fig)


def analyze_ic(df, col, cn_label, ic_dir):
    ic_s = calc_rank_ic(df, col)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(ic_s.index, ic_s.values, color='steelblue', lw=1.2, marker='o', ms=3)
    ax.axhline(0, color='gray', ls='--', lw=0.6)
    ax.axhline(ic_s.mean(), color='crimson', ls='-', lw=0.8, label=f'均值={ic_s.mean():.4f}')
    ax.set_title(f'{cn_label} — Rank IC 时序'); ax.set_ylabel('Rank IC'); ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(f'{ic_dir}/ic_ts.png', dpi=150); plt.close(fig)
    s = ic_s.dropna()
    with open(f'{ic_dir}/{col}_ic.txt', 'w') as f:
        ic_mean, ic_std = s.mean(), s.std()
        icir = ic_mean / ic_std if ic_std > 0 else np.nan
        t_stat = ic_mean / (ic_std / np.sqrt(len(s))) if ic_std > 0 else np.nan
        f.write(f'因子: {col} ({cn_label})\n样本数(月): {len(s)}\n')
        f.write(f'IC 均值: {ic_mean:.6f}\nIC 标准差: {ic_std:.6f}\nICIR: {icir:.4f}\nt 统计量: {t_stat:.4f}\n')
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(s, bins=20, color='steelblue', edgecolor='white', alpha=0.7)
    ax.axvline(0, color='gray', ls='--', lw=0.8)
    ax.axvline(ic_s.mean(), color='crimson', ls='-', lw=1.2, label=f'均值={ic_s.mean():.4f}')
    ax.set_xlabel('Rank IC'); ax.set_ylabel('频数'); ax.set_title(f'{cn_label} — IC 分布'); ax.legend()
    fig.tight_layout(); fig.savefig(f'{ic_dir}/ic_dist.png', dpi=150); plt.close(fig)
    ic_df = ic_s.reset_index(); ic_df.columns = ['TRADE_DATE', 'IC']
    ic_df['TRADE_DATE'] = ic_df['TRADE_DATE'].dt.strftime('%Y%m%d')
    ic_df.to_parquet(f'{ic_dir}/{col}_ic.parquet', index=False)


def analyze_ret(df, col, cn_label, ret_dir):
    decile_rets = calc_decile_rets(df, col)
    cum = (1 + decile_rets).cumprod()
    fig, ax = plt.subplots(figsize=(12, 4.5))
    cmap = plt.cm.RdYlBu_r
    for i in range(10):
        ax.plot(cum.index, cum[i], lw=1.3, color=cmap(i / 9), label=f'D{i+1}')
    ax.axhline(1, color='gray', ls='--', lw=0.6); ax.set_ylabel('净值')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.2f}'))
    ax.legend(fontsize=7, ncol=5); ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(f'{ret_dir}/ret_decile.png', dpi=150); plt.close(fig)


def analyze_rr(decile_rets, col, cn_label, rr_dir):
    d10 = decile_rets[9].dropna(); d1 = decile_rets[0].dropna()
    long_win = (d10 > 0).mean(); short_win = (d1 < 0).mean()
    full_win = (decile_rets > 0).mean()

    def tail_odds(s):
        pos = s[s > 0]; neg = s[s < 0]
        if len(pos) == 0 or len(neg) == 0: return np.nan
        return pos.mean() / abs(neg.mean())

    long_odds = tail_odds(d10); short_odds = tail_odds(-d1)
    with open(f'{rr_dir}/{col}_rr.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n样本数(月): {len(d10)}\n\n')
        f.write(f'{"指标":>12} {"多头(D10)":>12} {"空头(D1)":>12}\n')
        f.write(f'{"胜率":>12} {long_win:>12.4f} {short_win:>12.4f}\n')
        f.write(f'{"尾部赔率":>12} {long_odds:>12.4f} {short_odds:>12.4f}\n')


def analyze_sig(df, col, cn_label, sig_dir):
    vals = df[col].dropna()
    kurt_val = kurtosis(vals, fisher=True, bias=False)
    plot_kurtosis_hist(vals, cn_label, f'{sig_dir}/{col}_kurtosis.png')
    df_sorted = df.sort_values(['industry_code', 'TRADE_DATE'])
    def acf1(g):
        s = g[col].dropna()
        return s.autocorr(lag=1) if len(s) >= 10 else np.nan
    acf_vals = df_sorted.groupby('industry_code').apply(acf1, include_groups=False)
    with open(f'{sig_dir}/{col}_sig.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n有效样本(行业×月): {len(vals)}\n')
        f.write(f'行业数: {acf_vals.notna().sum()}\n\n')
        f.write(f'峰度 (超额): {kurt_val:.4f}\n')
        f.write(f'  → {"尖峰厚尾" if kurt_val > 0.5 else "低峰薄尾" if kurt_val < -0.3 else "接近正态"}\n\n')
        f.write(f'ACF(1) 均值: {acf_vals.mean():.4f}\n')


def monthly_fn(df, col, cn_label, cat, base_path):
    ic_dir = f'{base_path}/ic'; ret_dir = f'{base_path}/ret'
    rr_dir = f'{base_path}/rr'; sig_dir = f'{base_path}/sig'
    os.makedirs(ic_dir, exist_ok=True); os.makedirs(ret_dir, exist_ok=True)
    os.makedirs(rr_dir, exist_ok=True); os.makedirs(sig_dir, exist_ok=True)
    analyze_ic(df, col, cn_label, ic_dir)
    analyze_ret(df, col, cn_label, ret_dir)
    decile_rets = calc_decile_rets(df, col)
    analyze_rr(decile_rets, col, cn_label, rr_dir)
    ret_mean = decile_rets.mean()
    with open(f'{ret_dir}/{col}_ret.txt', 'w') as f:
        f.write(f'ret_D1={ret_mean[0]:.8f}\nret_D10={ret_mean[9]:.8f}\n'
                f'ret_spread={ret_mean[9] - ret_mean[0]:.8f}\n')
    analyze_sig(df, col, cn_label, sig_dir)
    print(f'  [{col}] 完成')


def main():
    df = pd.read_parquet(f'{data_dir}/industry_monthly_ratio.parquet')
    from analysis_base import run_analysis
    run_analysis(df, monthly_fn, 'monthly', date_col='ym', check_subdir='ic')


if __name__ == '__main__':
    main()
