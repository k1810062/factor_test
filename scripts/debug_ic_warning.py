"""临时测试：ma5_cross_ma20 IC 计算，追踪除零警告。"""
import sys, os, warnings
os.chdir('/Users/wby/k/factor_test/llm_factors')
sys.path.insert(0, 'src')

warnings.simplefilter('error')  # 把警告转成异常，精确定位

import pandas as pd, numpy as np
from scipy.stats import spearmanr

# 1. 读取已计算的因子值
df = pd.read_parquet('output/factor_library/stock_factors.parquet',
                     columns=['stock_code', 'trade_date', 'ma5_cross_ma20'])
print(f'因子值: {len(df)} 行')
print(f'值分布: {df["ma5_cross_ma20"].value_counts(dropna=False).to_dict()}')
print(f'日均唯一值数: {df.groupby("trade_date")["ma5_cross_ma20"].nunique().describe()}')

# 2. 读行情算前向收益
price = pd.read_parquet('data/stock_daily.parquet', columns=['stock_code', 'trade_date', 'close'])
merged = df.merge(price, on=['stock_code', 'trade_date'], how='inner')
merged = merged.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
g = merged.groupby('stock_code')['close']
merged['ret_T1'] = g.transform(lambda x: x.shift(-1) / x - 1)

# 3. 逐日算 IC
bad_dates = []
for date, grp in merged.groupby('trade_date'):
    vals = grp[['ma5_cross_ma20', 'ret_T1']].dropna()
    if len(vals) < 10:
        continue
    try:
        ic, _ = spearmanr(vals['ma5_cross_ma20'], vals['ret_T1'])
    except Exception as e:
        bad_dates.append((date, str(e), vals['ma5_cross_ma20'].nunique(), vals['ret_T1'].nunique()))
        continue
    if np.isnan(ic):
        bad_dates.append((date, 'NaN result', vals['ma5_cross_ma20'].nunique(), vals['ret_T1'].nunique()))

if bad_dates:
    print(f'\n❌ 有问题的日期: {len(bad_dates)}')
    for d, reason, nf, nr in bad_dates[:10]:
        print(f'  {d}: {reason} (factor_unique={nf}, ret_unique={nr})')
else:
    print('✅ 所有日期 IC 计算正常')

# 4. 找到 nuniq>=2 但 spearmanr 仍出错的日期
warnings.simplefilter('always')  # 恢复警告显示
print('\n--- 检查有唯一值但 spearmanr 仍报错的日期 ---')
for date, grp in merged.groupby('trade_date'):
    vals = grp[['ma5_cross_ma20', 'ret_T1']].dropna()
    if len(vals) < 10:
        continue
    nf = vals['ma5_cross_ma20'].nunique()
    nr = vals['ret_T1'].nunique()
    if nf >= 2 and nr >= 2:
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always')
                ic, _ = spearmanr(vals['ma5_cross_ma20'], vals['ret_T1'])
                if w:
                    print(f'{date}: nf={nf}, nr={nr}, 触发警告: {w[0].message}')
        except Exception as e:
            print(f'{date}: nf={nf}, nr={nr}, 报错: {e}')
