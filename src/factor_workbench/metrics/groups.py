"""分析组函数。每个组是一个自包含的分析单元（计算 → 画图 → 保存）。
签名统一：(df, factor_col, label, output_path, cfg, domain_cfg)
  cfg: 本组的参数（来自 domain_config）
  domain_cfg: domain 级参数（key_col 等）
"""

import warnings, json, os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.stats import spearmanr, norm

warnings.filterwarnings('ignore', message='An input array is constant')

_FONT = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['font.sans-serif'] = _FONT
plt.rcParams['axes.unicode_minus'] = False


# ── 工具 ──────────────────────────────────────────

def _nw_std(x, max_lag):
    T = len(x)
    mu = np.mean(x)
    gamma_0 = np.var(x, ddof=0)
    nw_var = gamma_0
    for k in range(1, min(max_lag + 1, T - 2)):
        cov = np.mean((x[k:] - mu) * (x[:-k] - mu))
        nw_var += 2 * (1 - k / (max_lag + 1)) * cov
    return np.sqrt(max(nw_var, 1e-10))


def _calc_rank_ic(df, factor_col, ret_col):
    dates, ics = [], []
    for date, grp in df.groupby('trade_date'):
        vals = grp[[factor_col, ret_col]].dropna()
        if len(vals) < 10 or vals[factor_col].nunique() < 2 or vals[ret_col].nunique() < 2:
            continue
        ic, _ = spearmanr(vals[factor_col], vals[ret_col])
        dates.append(date)
        ics.append(ic)
    return pd.Series(ics, index=pd.to_datetime(dates, format='%Y%m%d'))


def _calc_nw_icir(ic_series, horizon, ann_factor):
    s = ic_series.dropna()
    if len(s) < 10:
        return np.nan, np.nan, np.nan
    mu = np.mean(s)
    std = _nw_std(s.values, max(0, horizon - 1))
    icir = mu / std * ann_factor if std > 0 else np.nan
    return mu, std, icir


def _calc_decile_rets(df, col, n_groups=10, ret_col='ret_T1', step=1):
    """按截面分组算每组 mean 收益。step>1 时每 step 天取一次截面（非重叠调仓）。"""
    dates, rets = [], []
    all_dates = sorted(df['trade_date'].unique())
    for date in all_dates[::step]:
        grp = df[df['trade_date'] == date].dropna(subset=[col, ret_col])
        if len(grp) < 15:
            continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), n_groups, labels=False)
        rets.append(grp.groupby('decile')[ret_col].mean().values)
        dates.append(date)
    return pd.DataFrame(rets, index=pd.to_datetime(dates, format='%Y%m%d'))


# ── IC 组 ──────────────────────────────────────────

def run_ic(df, factor_col, label, output_path, cfg, domain_cfg):
    """Rank IC 分析。"""
    horizons = cfg.get('horizons', [1, 5, 10, 22])
    ann_factor = cfg.get('ann_factor', 252)

    ic_dir = os.path.join(output_path, 'ic')
    os.makedirs(ic_dir, exist_ok=True)

    ret_cols = [c for c in df.columns if c.startswith('ret_T')]
    available_h = sorted(
        int(c.split('_T')[1]) for c in ret_cols
        if int(c.split('_T')[1]) in horizons
    )
    if not available_h:
        print(f'  [{factor_col}] 无对应 ret_T 列，跳过 IC 分析')
        return

    ic_dict = {}
    for h in available_h:
        ic_dict[h] = _calc_rank_ic(df, factor_col, f'ret_T{h}')

    # ICIR + 保存 JSON
    horizons_data = []
    for h in available_h:
        hm, hs, hir = _calc_nw_icir(ic_dict[h], h, ann_factor)
        ht = hm / (hs / np.sqrt(len(ic_dict[h].dropna()))) if hs > 0 else 0
        horizons_data.append({
            'h': h, 'ic_mean': round(hm, 6), 'ic_std': round(hs, 6),
            'icir': round(hir, 4), 't_stat': round(ht, 4),
        })
    mu1, std1, icir1 = _calc_nw_icir(ic_dict[available_h[0]], available_h[0], ann_factor)
    t1 = mu1 / (std1 / np.sqrt(len(ic_dict[available_h[0]].dropna()))) if std1 > 0 else 0
    with open(os.path.join(ic_dir, f'{factor_col}_ic.json'), 'w') as f:
        json.dump({
            'name': factor_col, 'label': label,
            'n_months': len(ic_dict[available_h[0]].dropna()),
            'ic_mean': round(mu1, 6), 'ic_std': round(std1, 6),
            'icir': round(icir1, 4), 't_stat': round(t1, 4),
            'horizons': horizons_data,
        }, f, indent=2, ensure_ascii=False)

    # 图：累计 IC
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        ax.plot(ic_s.index, ic_s.cumsum().values, lw=1.5, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6)
    ax.set_ylabel('累计 Rank IC')
    ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout()
    fig.savefig(os.path.join(ic_dir, 'ic_cum.png'), dpi=150)
    plt.close(fig)

    # 图：IC 时序
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for (h, ic_s), c in zip(ic_dict.items(), colors):
        monthly = ic_s.resample('ME').mean()
        ax.plot(ic_s.index, ic_s.values, alpha=0.15, lw=0.5, color=c)
        ax.plot(monthly.index, monthly.values, lw=1.8, color=c, label=f'T+{h}')
    ax.axhline(0, color='gray', ls='--', lw=0.6)
    ax.set_ylabel('Rank IC')
    ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout()
    fig.savefig(os.path.join(ic_dir, 'ic_ts.png'), dpi=150)
    plt.close(fig)

    # 图：IC 对比（均值/标准差/ICIR）
    hs = sorted(ic_dict.keys())
    means, stds, icirs = [], [], []
    for h in hs:
        mu, sd, _ = _calc_nw_icir(ic_dict[h], h, ann_factor)
        means.append(mu)
        stds.append(sd)
        icirs.append(mu / sd if sd > 0 else np.nan)
    x = np.arange(len(hs))
    w = 0.28
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    a1.bar(x - w, means, w, label='IC 均值', color='steelblue')
    a1.bar(x, stds, w, label='IC 标准差', color='lightcoral')
    a1.set_title(f'{label} — IC 汇总')
    a1.legend(fontsize=9)
    a1.axhline(0, ls=':', lw=0.6)
    a2.bar(x, icirs, w * 1.5, color='darkgreen', label='ICIR')
    a2.set_xticks(x)
    a2.set_xticklabels([f'T+{h}' for h in hs])
    a2.legend(fontsize=9)
    a2.axhline(0, ls=':', lw=0.6)
    fig.tight_layout()
    fig.savefig(os.path.join(ic_dir, 'ic_comp.png'), dpi=150)
    plt.close(fig)

    # 图：IC 分布
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for (h, ic_s), c, ax in zip(ic_dict.items(), colors, axes.flat):
        vals = ic_s.dropna()
        ax.hist(vals, bins=40, color=c, alpha=0.7, edgecolor='white')
        ax.axvline(0, color='gray', ls='--', lw=0.8)
        ax.axvline(vals.mean(), color='crimson', ls='-', lw=1.2, label=f'均值={vals.mean():.4f}')
        ax.set_title(f'T+{h}')
        ax.set_xlabel('Rank IC')
        ax.set_ylabel('频数')
        ax.legend(fontsize=8)
    fig.suptitle(f'{label} — IC 分布', fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(ic_dir, 'ic_dist.png'), dpi=150)
    plt.close(fig)

    # IC 数据 parquet
    ic_df = pd.DataFrame({f'T+{h}': ic_dict[h] for h in available_h}).reset_index()
    ic_df.columns = ['trade_date'] + [f'T+{h}' for h in available_h]
    ic_df['trade_date'] = ic_df['trade_date'].dt.strftime('%Y%m%d')
    ic_df.to_parquet(os.path.join(ic_dir, f'{factor_col}_ic.parquet'), index=False)

    print(f'  [{factor_col}] IC 完成 (n_ic={len(ic_dict[available_h[0]].dropna())})')


# ── 十分组组 ──────────────────────────────────────

def run_decile(df, factor_col, label, output_path, cfg, domain_cfg):
    """十分组收益分析。支持 horizons 列表，每个周期独立保存。"""
    n_groups = cfg.get('n_groups', 10)
    horizons = cfg.get('horizons', [cfg.get('ret_horizon', 1)])
    if isinstance(horizons, int):
        horizons = [horizons]

    ret_dir = os.path.join(output_path, 'ret')
    os.makedirs(ret_dir, exist_ok=True)

    for h in horizons:
        ret_col = f'ret_T{h}'
        if ret_col not in df.columns:
            continue
        step = cfg.get('step', h)
        decile_rets = _calc_decile_rets(df, factor_col, n_groups, ret_col, step=step)
        if len(decile_rets) == 0:
            continue

        suffix = f'_T{h}' if len(horizons) > 1 else ''

        # 保存 parquet
        decile_rets.to_parquet(os.path.join(ret_dir, f'{factor_col}_decile_rets{suffix}.parquet'), index=True)

        # 图：累计收益
        cum = (1 + decile_rets).cumprod() - 1
        fig, ax = plt.subplots(figsize=(12, 4.5))
        for i in range(n_groups):
            ax.plot(cum.index, cum[i], lw=1.3,
                    color=plt.cm.RdYlBu_r(i / (n_groups - 1)), label=f'D{i+1}')
        ax.axhline(0, color='gray', ls='--', lw=0.6)
        ax.set_ylabel('累计收益')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
        ax.legend(fontsize=7, ncol=5)
        fig.tight_layout()
        fig.savefig(os.path.join(ret_dir, f'ret_decile{suffix}.png'), dpi=150)
        plt.close(fig)

        # 图：日均收益柱状
        means = decile_rets.mean() * 100
        fig, ax = plt.subplots(figsize=(8, 4.5))
        colors_bar = [plt.cm.RdYlBu_r(i / (n_groups - 1)) for i in range(n_groups)]
        ax.bar(range(n_groups), means.values, color=colors_bar, width=0.6, edgecolor='white')
        ax.axhline(0, color='gray', ls=':', lw=0.6)
        ax.set_xticks(range(n_groups))
        ax.set_xticklabels([f'D{i+1}' for i in range(n_groups)])
        ax.set_ylabel('日均收益率（%）')
        ax.set_title(f'{label} — T+{h} 分位数组平均收益')
        fig.tight_layout()
        fig.savefig(os.path.join(ret_dir, f'ret_decile_bar{suffix}.png'), dpi=150)
        plt.close(fig)

        # 图：多空累计
        lc = (1 + decile_rets[n_groups - 1]).cumprod() - 1
        sc = (1 + decile_rets[0]).cumprod() - 1
        spc = (1 + (decile_rets[n_groups - 1] - decile_rets[0])).cumprod() - 1
        fig, ax = plt.subplots(figsize=(12, 4.5))
        ax.plot(lc.index, lc.values, lw=1.5, color='crimson', label=f'多头(D{n_groups})')
        ax.plot(sc.index, sc.values, lw=1.5, color='steelblue', label='空头(D1)')
        ax.plot(spc.index, spc.values, lw=2, color='darkgreen', label='多空')
        ax.axhline(0, color='gray', ls=':', lw=0.6)
        ax.set_ylabel('累计收益')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
        ax.legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(ret_dir, f'ret_long_short{suffix}.png'), dpi=150)
        plt.close(fig)

        # ret JSON（只在第一个 horizon 保存）
        if suffix == '' or h == horizons[0]:
            ret_mean = decile_rets.mean()
            with open(os.path.join(ret_dir, f'{factor_col}_ret.json'), 'w') as f:
                json.dump({
                    'ret_D1': round(float(ret_mean[0]), 8),
                    f'ret_D{n_groups}': round(float(ret_mean[n_groups - 1]), 8),
                    'ret_spread': round(float(ret_mean[n_groups - 1] - ret_mean[0]), 8),
                }, f, indent=2, ensure_ascii=False)

        print(f'  [{factor_col}] 十分组 T+{h} 完成 (step={step}, n_dates={len(decile_rets)})')


# ── 统计特征组 ──────────────────────────────────────

def run_sig(df, factor_col, label, output_path, cfg, domain_cfg):
    """统计特征：峰度 + ACF(1)。"""
    key_col = domain_cfg.get('key_col', 'stock_code')

    sub_dir = os.path.join(output_path, 'sig')
    os.makedirs(sub_dir, exist_ok=True)
    valid = df[factor_col].dropna()

    if len(valid) == 0:
        print(f'  [{factor_col}] 无有效数据，跳过 sig')
        return

    excess_kurt = valid.kurtosis()
    n_ind = df[key_col].nunique()
    acf1_by_ind = []
    for code, grp in df.groupby(key_col):
        s = grp[factor_col].dropna()
        if len(s) < 10 or s.std() == 0:
            continue
        # autocorr 内部用 np.corrcoef，切片也可能零方差
        s1, s2 = s[:-1], s[1:]
        if len(s1) < 2 or s1.std() == 0 or s2.std() == 0:
            continue
        lag1_corr = s.autocorr(lag=1)
        if not np.isnan(lag1_corr):
            acf1_by_ind.append(lag1_corr)

    acf1_mean = np.mean(acf1_by_ind) if acf1_by_ind else np.nan
    acf1_std = np.std(acf1_by_ind) if acf1_by_ind else np.nan

    # JSON
    with open(os.path.join(sub_dir, f'{factor_col}_sig.json'), 'w') as f:
        d = {'excess_kurt': round(excess_kurt, 4), 'n_industries': n_ind,
             'acf1_mean': round(acf1_mean, 6), 'acf1_std': round(acf1_std, 6)}
        if acf1_by_ind:
            d['acf1_p25'] = round(float(np.percentile(acf1_by_ind, 25)), 6)
            d['acf1_p50'] = round(float(np.percentile(acf1_by_ind, 50)), 6)
            d['acf1_p75'] = round(float(np.percentile(acf1_by_ind, 75)), 6)
        json.dump(d, f, indent=2, ensure_ascii=False)

    # 图
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(valid, bins=50, density=True, alpha=0.7, color='steelblue',
            edgecolor='white', label='实际分布')
    x_range = np.linspace(valid.min(), valid.max(), 200)
    ax.plot(x_range, norm.pdf(x_range, valid.mean(), valid.std()),
            'r-', lw=2, label='正态分布')
    ax.set_xlabel(label)
    ax.set_ylabel('密度')
    ax.set_title(f'{label} — 峰度={excess_kurt:.3f}')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(sub_dir, f'{factor_col}_kurtosis.png'), dpi=150)
    plt.close(fig)

    kurt_desc = '尖峰厚尾' if excess_kurt > 0.5 else ('低峰薄尾' if excess_kurt < -0.3 else '接近正态')
    print(f'  [{factor_col}] sig 完成: 峰度={excess_kurt:.3f}, ACF(1)={acf1_mean:.3f} ({kurt_desc})')


# ── 胜率组 ──────────────────────────────────────────

def run_rr(df, factor_col, label, output_path, cfg, domain_cfg):
    """胜率 + 尾部赔率分析。"""
    ret_horizon = cfg.get('ret_horizon', 1)
    ret_col = f'ret_T{ret_horizon}'

    if ret_col not in df.columns:
        return

    sub_dir = os.path.join(output_path, 'rr')
    os.makedirs(sub_dir, exist_ok=True)

    long_wins, short_wins = [], []
    long_odds_list, short_odds_list = [], []
    win_rate_buckets = [[] for _ in range(10)]

    for date, grp in df.groupby('trade_date'):
        grp = grp.dropna(subset=[factor_col, ret_col])
        if len(grp) < 15:
            continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[factor_col].rank(method='first'), 10, labels=False)
        d_ret = grp.groupby('decile')[ret_col]

        long_wins.append((d_ret.mean().loc[9] > 0))
        short_wins.append((d_ret.mean().loc[0] > 0))

        long_top = d_ret.mean().loc[9]
        short_top = d_ret.mean().loc[0]
        long_bot = d_ret.mean().loc[0:2].mean()
        short_bot = d_ret.mean().loc[7:9].mean()
        if long_bot != 0:
            long_odds_list.append(long_top / long_bot)
        if short_bot != 0:
            short_odds_list.append(short_top / short_bot)

        for i in range(10):
            win_rate_buckets[i].append(d_ret.mean().iloc[i] > 0)

    long_win = np.mean(long_wins) if long_wins else np.nan
    short_win = np.mean(short_wins) if short_wins else np.nan
    long_odds = np.mean(long_odds_list) if long_odds_list else np.nan
    short_odds = np.mean(short_odds_list) if short_odds_list else np.nan

    # JSON
    with open(os.path.join(sub_dir, f'{factor_col}_rr.json'), 'w') as f:
        json.dump({
            'long_win': round(long_win, 6),
            'short_win': round(short_win, 6),
            'long_odds': round(long_odds, 4),
            'short_odds': round(short_odds, 4),
        }, f, indent=2, ensure_ascii=False)

    # 图：分位数组胜率
    wr_means = [np.mean(w) for w in win_rate_buckets] if win_rate_buckets else []
    if wr_means:
        fig, ax = plt.subplots(figsize=(8, 4))
        colors_bar = [plt.cm.RdYlBu_r(i / 9) for i in range(10)]
        ax.bar(range(10), wr_means, color=colors_bar, width=0.6, edgecolor='white')
        ax.axhline(0.5, color='gray', ls='--', lw=0.8)
        ax.set_xticks(range(10))
        ax.set_xticklabels([f'D{i+1}' for i in range(10)])
        ax.set_ylabel('胜率')
        ax.set_title('十分组胜率')
        fig.tight_layout()
        fig.savefig(os.path.join(sub_dir, 'win_rate_decile.png'), dpi=150)
        plt.close(fig)

    # 图：尾部赔率
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(['多头(D10)', '空头(D1)'], [long_odds, short_odds],
           color=['crimson', 'steelblue'], width=0.5)
    ax.set_ylabel('尾部赔率')
    ax.axhline(1, color='gray', ls='--', lw=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(sub_dir, 'tail_odds.png'), dpi=150)
    plt.close(fig)

    print(f'  [{factor_col}] rr 完成: 多头胜率={long_win:.2%}, 空头胜率={short_win:.2%}')


# ── 时序统计组 ──────────────────────────────────────

def run_ts(df, factor_col, label, output_path, cfg, domain_cfg):
    """时序均值 + 描述统计。"""
    show_industry_bar = cfg.get('show_industry_bar', False)
    key_col = domain_cfg.get('key_col', 'stock_code')

    sub_dir = os.path.join(output_path, 'charts')
    os.makedirs(sub_dir, exist_ok=True)
    base = os.path.join(sub_dir, factor_col)
    valid = df[factor_col].dropna()

    if len(valid) == 0:
        print(f'  [{factor_col}] 无有效数据，跳过 ts')
        return

    stats = valid.describe()
    with open(f'{base}.txt', 'w') as f:
        f.write(f'因子: {factor_col} ({label})\n')
        f.write(f'日期范围: {df["trade_date"].min()} ~ {df["trade_date"].max()}\n')
        f.write(f'总样本数: {len(df)}\n')
        f.write(f'有效样本: {len(valid)}\n')
        f.write(f'缺失样本: {df[factor_col].isna().sum()}\n\n')
        f.write('统计描述:\n')
        for k in ['mean', 'std', 'min', '25%', '50%', '75%', 'max']:
            f.write(f'  {k}: {stats[k]:.6f}\n')

    # 图：分布
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(valid, bins=50, color='steelblue', edgecolor='white', alpha=0.85)
    ax.axvline(valid.mean(), color='crimson', ls='--', lw=1.2, label=f'均值={valid.mean():.4f}')
    ax.set_xlabel(label)
    ax.set_ylabel('频数')
    ax.set_title(f'{label} 分布')
    ax.legend()
    fig.tight_layout()
    fig.savefig(f'{base}_hist.png', dpi=150)
    plt.close(fig)

    # 图：时序
    daily_mean = df.groupby('trade_date')[factor_col].mean()
    dates = pd.to_datetime(daily_mean.index.astype(str), format='%Y%m%d')
    monthly = daily_mean.copy()
    monthly.index = dates
    monthly = monthly.resample('ME').mean()
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(dates, daily_mean.values, alpha=0.25, lw=0.6, color='steelblue', label='日线')
    ax.plot(monthly.index, monthly.values, lw=1.8, color='crimson', label='月均线')
    ax.axhline(daily_mean.mean(), color='gray', ls=':', lw=0.8)
    ax.set_xlabel('日期')
    ax.set_ylabel(label)
    ax.set_title(f'{label} 时序')
    ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout()
    fig.savefig(f'{base}_ts.png', dpi=150)
    plt.close(fig)

    # 行业均值图（仅 industry domain 需要）
    if show_industry_bar and 'industry' in df.columns:
        ind_mean = df.groupby('industry')[factor_col].mean().sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(10, 6))
        colors_bar = ['crimson' if v >= 0 else 'steelblue' for v in ind_mean.values]
        ax.barh(range(len(ind_mean)), ind_mean.values, color=colors_bar, height=0.65)
        ax.set_yticks(range(len(ind_mean)))
        ax.set_yticklabels(ind_mean.index, fontsize=8)
        ax.set_xlabel(label)
        ax.set_title(f'{label} — 行业均值')
        ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(f'{base}_ind_bar.png', dpi=150, bbox_inches='tight')
        plt.close(fig)

    print(f'  [{factor_col}] ts 完成')


# ── 注册表 ──────────────────────────────────────────

ANALYSIS_GROUPS = {
    'ic': run_ic,
    'decile': run_decile,
    'sig': run_sig,
    'rr': run_rr,
    'ts': run_ts,
}
