"""峰度 + ACF(1) 分析。"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from scipy.stats import kurtosis

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

data_dir = 'output/data_processed'


def plot_kurtosis_hist(series, label, save_path):
    s = series.dropna()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(s, bins=60, color='steelblue', density=True, alpha=0.7, edgecolor='white')
    mu, std = s.mean(), s.std()
    x = np.linspace(s.min(), s.max(), 200)
    ax.plot(x, 1 / (std * np.sqrt(2 * np.pi)) * np.exp(-(x - mu)**2 / (2 * std**2)), 'r--', lw=1.5, label='正态分布')
    ax.axvline(mu, color='crimson', ls='-', lw=1, label=f'均值={mu:.4f}')
    ax.set_xlabel('因子值'); ax.set_ylabel('密度'); ax.set_title(f'{label} — 分布 vs 正态'); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(save_path, dpi=150); plt.close(fig)


def calc_acf1(group, col):
    s = group[col].dropna()
    return s.autocorr(lag=1) if len(s) >= 10 else np.nan


def sig_fn(df, col, cn_label, cat, base_path):
    sig_dir = f'{base_path}/sig'; os.makedirs(sig_dir, exist_ok=True)
    vals = df[col].dropna()
    kurt_val = kurtosis(vals, fisher=True, bias=False)
    plot_kurtosis_hist(vals, cn_label, f'{sig_dir}/{col}_kurtosis.png')

    df_sorted = df.sort_values(['industry_code', 'TRADE_DATE'])
    acf_vals = df_sorted.groupby('industry_code').apply(lambda g: calc_acf1(g, col), include_groups=False)
    acf_mean = acf_vals.mean(); acf_std = acf_vals.std()
    acf_q25 = acf_vals.quantile(0.25); acf_q75 = acf_vals.quantile(0.75)

    with open(f'{sig_dir}/{col}_sig.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n有效样本数: {len(vals)}\n')
        f.write(f'行业数: {acf_vals.notna().sum()}\n\n')
        f.write(f'峰度 (超额): {kurt_val:.4f}\n')
        f.write(f'  → {"尖峰厚尾" if kurt_val > 0.5 else "低峰薄尾" if kurt_val < -0.3 else "接近正态"}\n\n')
        f.write(f'ACF(1) 均值: {acf_mean:.4f}\n标准差: {acf_std:.4f}\n25%分位: {acf_q25:.4f}\n75%分位: {acf_q75:.4f}\n')
    print(f'  [{col}] 完成: 峰度={kurt_val:.3f}, ACF(1)={acf_mean:.3f}')


def main():
    df = pd.read_parquet(f'{data_dir}/industry_daily_ratio.parquet')
    from analysis_base import run_analysis
    run_analysis(df, sig_fn, 'industry', check_subdir='sig')


if __name__ == '__main__':
    main()
