"""胜率 + 尾部赔率分析。@metric 装饰器注册。"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os, json
from ..engine.registry import metric

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False


def _calc_rr(df, col, base_path):
    sub_dir = f'{base_path}/rr'
    os.makedirs(sub_dir, exist_ok=True)

    long_wins, short_wins = [], []
    long_odds_list, short_odds_list = [], []

    for date, grp in df.groupby('trade_date'):
        grp = grp.dropna(subset=[col, 'ret_T1'])
        if len(grp) < 15:
            continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), 10, labels=False)
        d_ret = grp.groupby('decile')['ret_T1']

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

    long_win = np.mean(long_wins) if long_wins else np.nan
    short_win = np.mean(short_wins) if short_wins else np.nan
    long_odds = np.mean(long_odds_list) if long_odds_list else np.nan
    short_odds = np.mean(short_odds_list) if short_odds_list else np.nan

    with open(f'{sub_dir}/{col}_rr.json', 'w') as f:
        json.dump({
            'long_win': round(long_win, 6),
            'short_win': round(short_win, 6),
            'long_odds': round(long_odds, 4),
            'short_odds': round(short_odds, 4),
        }, f, indent=2, ensure_ascii=False)

    win_rates = []
    for date, grp in df.groupby('trade_date'):
        grp = grp.dropna(subset=[col, 'ret_T1'])
        if len(grp) < 15:
            continue
        grp = grp.copy()
        grp['decile'] = pd.qcut(grp[col].rank(method='first'), 10, labels=False)
        d_ret = grp.groupby('decile')['ret_T1'].mean()
        for i in range(10):
            if len(win_rates) <= i:
                win_rates.append([])
            win_rates[i].append(d_ret.iloc[i] > 0)

    fig, ax = plt.subplots(figsize=(8, 4))
    wr_means = [np.mean(w) for w in win_rates] if win_rates else []
    if wr_means:
        colors = [plt.cm.RdYlBu_r(i / 9) for i in range(10)]
        ax.bar(range(10), wr_means, color=colors, width=0.6, edgecolor='white')
        ax.axhline(0.5, color='gray', ls='--', lw=0.8)
        ax.set_xticks(range(10)); ax.set_xticklabels([f'D{i+1}' for i in range(10)])
        ax.set_ylabel('胜率'); ax.set_title('十分组胜率')
        fig.tight_layout(); fig.savefig(f'{sub_dir}/win_rate_decile.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(['多头(D10)', '空头(D1)'], [long_odds, short_odds],
           color=['crimson', 'steelblue'], width=0.5)
    ax.set_ylabel('尾部赔率'); ax.axhline(1, color='gray', ls='--', lw=0.8)
    fig.tight_layout(); fig.savefig(f'{sub_dir}/tail_odds.png', dpi=150)
    plt.close(fig)

    return long_win, short_win, long_odds, short_odds


@metric(name='rr', label='胜率分析')
def rr_metric(df, col, cn_label, cat, base_path, domain):
    long_win, short_win, long_odds, short_odds = _calc_rr(df, col, base_path)
    print(f'  [{col}] 完成: 多头胜率={long_win:.2%}, 空头胜率={short_win:.2%}')
