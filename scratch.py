"""
草稿因子 → 追加到因子库 → 改配置 → 跑 main。

用法：
    python3 scratch.py factors/scratch/my_factor.py
"""

import sys, os, json, re

sys.path.insert(0, os.path.dirname(__file__))

FACTOR_FILES = {
    'stock':    'factors/stock_factors.py',
    'industry': 'factors/industry_factors.py',
    'monthly':  'factors/monthly_factors.py',
}

CONFIG_PATH = 'config/config.json'


def main():
    path = sys.argv[1]
    code = open(path).read()

    factors = re.findall(
        r"@factor\(name='(\w+)',\s*category='(\w+)',\s*label='(.+?)',\s*domain='(\w+)'",
        code)

    # 追加到因子库
    target = FACTOR_FILES.get(factors[0][3], FACTOR_FILES['industry'])
    existing = open(target).read()
    for name, cat, label, domain in factors:
        if f"@factor(name='{name}'" in existing:
            print(f'  [{name}] 已存在，跳过')
            continue
        with open(target, 'a') as f:
            f.write('\n\n# ─── 新增草稿因子 ───\n' + code.strip() + '\n')
        print(f'  [{name}] → 已加入因子库')

    # 改配置只留新因子
    cfg = {domain: {} for _, _, _, domain in factors}
    for name, cat, label, domain in factors:
        cfg[domain][name] = {'cat': cat, 'label': label}
    cfg['analysis'] = ['charts', 'ic', 'rr', 'sig']
    cfg['sub_period'] = {'from_file': 'data/market_periods.json', 'groups': ['bull', 'bear', 'consolidate']}
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'  → config.json 已改写（只保留新因子）')

    # 跑 main
    print('\n=== 运行 main.py ===')
    os.system('python3 main.py')


if __name__ == '__main__':
    main()
