"""峰度 + ACF(1) 分析。@metric 装饰器注册。"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from scipy.stats import norm
from framework.registry import metric

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False


@metric(name='sig', label='统计特征分析')
def sig_metric(df, col, cn_label, cat, base_path):
    sub_dir = f'{base_path}/sig'
    os.makedirs(sub_dir, exist_ok=True)
    base = f'{sub_dir}/{col}'
    valid = df[col].dropna()

    if len(valid) == 0:
        print(f'  [{col}] 无有效数据，跳过')
        return

    excess_kurt = valid.kurtosis()

    n_ind = df['industry_code'].nunique()
    acf1_by_ind = []
    for code, grp in df.groupby('industry_code'):
        s = grp[col].dropna()
        if len(s) < 10:
            continue
        lag1_corr = s.autocorr(lag=1)
        if not np.isnan(lag1_corr):
            acf1_by_ind.append(lag1_corr)

    acf1_mean = np.mean(acf1_by_ind) if acf1_by_ind else np.nan
    acf1_std = np.std(acf1_by_ind) if acf1_by_ind else np.nan

    with open(f'{base}_sig.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n')
        f.write(f'超额峰度: {excess_kurt:.4f}\n')
        f.write(f'行业数: {n_ind}\n')
        f.write(f'ACF(1) 均值: {acf1_mean:.6f}\n')
        f.write(f'ACF(1) 标准差: {acf1_std:.6f}\n')
        if acf1_by_ind:
            f.write(f'ACF(1) 25%分位: {np.percentile(acf1_by_ind, 25):.6f}\n')
            f.write(f'ACF(1) 50%分位: {np.percentile(acf1_by_ind, 50):.6f}\n')
            f.write(f'ACF(1) 75%分位: {np.percentile(acf1_by_ind, 75):.6f}\n')

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(valid, bins=50, density=True, alpha=0.7, color='steelblue', edgecolor='white', label='实际分布')
    x_range = np.linspace(valid.min(), valid.max(), 200)
    ax.plot(x_range, norm.pdf(x_range, valid.mean(), valid.std()),
            'r-', lw=2, label='正态分布')
    ax.set_xlabel(cn_label); ax.set_ylabel('密度')
    ax.set_title(f'{cn_label} — 峰度={excess_kurt:.3f}')
    ax.legend()
    fig.tight_layout(); fig.savefig(f'{base}_kurtosis.png', dpi=150)
    plt.close(fig)

    kurt_desc = '尖峰厚尾' if excess_kurt > 0.5 else ('低峰薄尾' if excess_kurt < -0.3 else '接近正态')
    print(f'  [{col}] 完成: 峰度={excess_kurt:.3f}, ACF(1)={acf1_mean:.3f} ({kurt_desc})')
