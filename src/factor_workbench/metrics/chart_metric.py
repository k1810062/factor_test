"""图表评价指标。@metric 装饰器注册。"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
from ..engine.registry import metric

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False


@metric(name='charts', label='因子统计图')
def chart_metric(df, col, cn_label, cat, base_path, domain):
    """生成单个因子的统计图。"""
    sub_dir = f'{base_path}/charts'
    os.makedirs(sub_dir, exist_ok=True)
    base = f'{sub_dir}/{col}'
    valid = df[col].dropna()

    if len(valid) == 0:
        print(f'  [{col}] 该时间段无有效数据，跳过')
        return

    stats = valid.describe()
    with open(f'{base}.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n')
        f.write(f'日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}\n')
        f.write(f'总样本数: {len(df)}\n')
        f.write(f'有效样本: {len(valid)}\n')
        f.write(f'缺失样本: {df[col].isna().sum()}\n\n')
        f.write('统计描述:\n')
        for k in ['mean', 'std', 'min', '25%', '50%', '75%', 'max']:
            f.write(f'  {k}: {stats[k]:.6f}\n')

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(valid, bins=50, color='steelblue', edgecolor='white', alpha=0.85)
    ax.axvline(valid.mean(), color='crimson', ls='--', lw=1.2, label=f'均值={valid.mean():.4f}')
    ax.set_xlabel(cn_label); ax.set_ylabel('频数'); ax.set_title(f'{cn_label} 分布')
    ax.legend()
    fig.tight_layout(); fig.savefig(f'{base}_hist.png', dpi=150); plt.close(fig)

    daily_mean = df.groupby('trade_date')[col].mean()
    dates = pd.to_datetime(daily_mean.index.astype(str), format='%Y%m%d')
    monthly = daily_mean.copy(); monthly.index = dates
    monthly = monthly.resample('ME').mean()
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(dates, daily_mean.values, alpha=0.25, lw=0.6, color='steelblue', label='日线')
    ax.plot(monthly.index, monthly.values, lw=1.8, color='crimson', label='月均线')
    ax.axhline(daily_mean.mean(), color='gray', ls=':', lw=0.8)
    ax.set_xlabel('日期'); ax.set_ylabel(cn_label); ax.set_title(f'{cn_label} 时序')
    ax.legend(fontsize=9); ax.xaxis.set_major_locator(mticker.MaxNLocator(8))
    fig.tight_layout(); fig.savefig(f'{base}_ts.png', dpi=150); plt.close(fig)

    if not domain.startswith('stock'):
        ind_mean = df.groupby('industry')[col].mean().sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['crimson' if v >= 0 else 'steelblue' for v in ind_mean.values]
        ax.barh(range(len(ind_mean)), ind_mean.values, color=colors, height=0.65)
        ax.set_yticks(range(len(ind_mean))); ax.set_yticklabels(ind_mean.index, fontsize=8)
        ax.set_xlabel(cn_label); ax.set_title(f'{cn_label} — 行业均值'); ax.invert_yaxis()
        fig.tight_layout(); fig.savefig(f'{base}_ind_bar.png', dpi=150, bbox_inches='tight')
        plt.close(fig)

    print(f'  [{col}] 完成')
