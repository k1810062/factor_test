"""胜率 + 尾部赔率分析。"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

data_dir = 'output/data_processed'


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


def rr_fn(df, col, cn_label, cat, base_path):
    rr_dir = f'{base_path}/rr'; os.makedirs(rr_dir, exist_ok=True)
    decile_rets = calc_decile_rets(df, col)
    d10 = decile_rets[9].dropna(); d1 = decile_rets[0].dropna()
    long_win = (d10 > 0).mean(); short_win = (d1 < 0).mean()
    full_win = (decile_rets > 0).mean()

    def tail_odds(s):
        pos = s[s > 0]; neg = s[s < 0]
        if len(pos) == 0 or len(neg) == 0: return np.nan
        return pos.mean() / abs(neg.mean())

    long_odds = tail_odds(d10); short_odds = tail_odds(-d1)

    with open(f'{rr_dir}/{col}_rr.txt', 'w') as f:
        f.write(f'因子: {col} ({cn_label})\n样本天数(T+1): {len(d10)}\n\n')
        f.write(f'{"指标":>12} {"多头(D10)":>12} {"空头(D1)":>12}\n')
        f.write(f'{"胜率":>12} {long_win:>12.4f} {short_win:>12.4f}\n')
        f.write(f'{"尾部赔率":>12} {long_odds:>12.4f} {short_odds:>12.4f}\n')

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [plt.cm.RdYlBu_r(i / 9) for i in range(10)]
    ax.bar(range(10), full_win.values, color=colors, width=0.6, edgecolor='white')
    ax.axhline(0.5, color='gray', ls='--', lw=0.8, label='50%')
    ax.set_xticks(range(10)); ax.set_xticklabels([f'D{i+1}' for i in range(10)])
    ax.set_ylabel('胜率'); ax.set_title(f'{cn_label} — 十分组胜率'); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(f'{rr_dir}/win_rate_decile.png', dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(['多头(D10)', '空头(D1)'], [long_odds, short_odds],
                  color=['crimson', 'steelblue'], width=0.5, edgecolor='white')
    ax.axhline(1, color='gray', ls='--', lw=0.8, label='盈亏平衡')
    for b, v in zip(bars, [long_odds, short_odds]):
        if not np.isnan(v): ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.05, f'{v:.2f}', ha='center')
    ax.set_ylabel('尾部赔率'); ax.set_title(f'{cn_label} — 多空尾部赔率'); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(f'{rr_dir}/tail_odds.png', dpi=150); plt.close(fig)
    print(f'  [{col}] 完成: 多头胜率={long_win:.2%}, 空头胜率={short_win:.2%}')


def main():
    df = pd.read_parquet(f'{data_dir}/industry_daily_ratio.parquet')
    idx = pd.read_parquet('data/SWI_daily.parquet',
                          columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
    idx = idx.rename(columns={'STOCK_CODE': 'industry_code', 'CLOSE': 'idx_close'})
    df = df.merge(idx, on=['industry_code', 'TRADE_DATE'], how='inner')
    df = df.sort_values(['industry_code', 'TRADE_DATE']).reset_index(drop=True)
    df['ret_t1'] = df.groupby('industry_code')['idx_close'].transform(lambda x: x.shift(-1) / x - 1)
    from analysis_base import run_analysis
    run_analysis(df, rr_fn, 'industry', check_subdir='rr')


if __name__ == '__main__':
    main()
