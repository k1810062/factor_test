"""峰度 + ACF(1) 分析。@metric 装饰器注册。"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os, json
from scipy.stats import norm
from ..engine.registry import metric

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False


@metric(name='sig', label='统计特征分析')
def sig_metric(df, col, cn_label, cat, base_path, domain):
    sub_dir = f'{base_path}/sig'
    os.makedirs(sub_dir, exist_ok=True)
    base = f'{sub_dir}/{col}'
    valid = df[col].dropna()

    if len(valid) == 0:
        print(f'  [{col}] 无有效数据，跳过')
        return

    excess_kurt = valid.kurtosis()

    grp_col = 'stock_code' if domain.startswith('stock') else 'industry_code'
    grp_label = '股票' if domain.startswith('stock') else '行业'
    n_ind = df[grp_col].nunique()
    acf1_by_ind = []
    for code, grp in df.groupby(grp_col):
        s = grp[col].dropna()
        if len(s) < 10:
            continue
        lag1_corr = s.autocorr(lag=1)
        if not np.isnan(lag1_corr):
            acf1_by_ind.append(lag1_corr)

    acf1_mean = np.mean(acf1_by_ind) if acf1_by_ind else np.nan
    acf1_std = np.std(acf1_by_ind) if acf1_by_ind else np.nan

    with open(f'{base}_sig.json', 'w') as f:
        d = {'excess_kurt': round(excess_kurt, 4), 'n_industries': n_ind,
             'acf1_mean': round(acf1_mean, 6), 'acf1_std': round(acf1_std, 6)}
        if acf1_by_ind:
            d['acf1_p25'] = round(float(np.percentile(acf1_by_ind, 25)), 6)
            d['acf1_p50'] = round(float(np.percentile(acf1_by_ind, 50)), 6)
            d['acf1_p75'] = round(float(np.percentile(acf1_by_ind, 75)), 6)
        json.dump(d, f, indent=2, ensure_ascii=False)

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
