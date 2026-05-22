"""
草稿因子 → 追加到因子库 → 改配置 → 跑 pipeline。

用法：
    python3 scratch.py my_factor.py              自动注册到因子库并跑分析
    python3 scratch.py --force my_factor.py      覆盖重算分析
"""

import sys, os, json, re

sys.path.insert(0, os.path.dirname(__file__))

CONFIG_PATH = 'config/config.json'
_CFG = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
_FACTOR_DIR = _CFG.get('factor_dir', 'factors')

FACTOR_FILES = {
    'stock':    f'{_FACTOR_DIR}/stock_factors.py',
    'industry': f'{_FACTOR_DIR}/industry_factors.py',
    'monthly':  f'{_FACTOR_DIR}/monthly_factors.py',
}


def main():
    path = sys.argv[2] if '--force' in sys.argv else sys.argv[1]
    code = open(path).read()

    factors = re.findall(
        r"@factor\(name='(\w+)',\s*category='(\w+)',\s*label='(.+?)',\s*domain='(\w+)'",
        code)

    if not factors:
        print('错误：未识别到 @factor 装饰器')
        print('文件内容:')
        print(code[:500])
        sys.exit(1)

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

    # 写 factors_config.json
    fc_path = 'config/factors_config.json'
    fc = {}
    if os.path.exists(fc_path):
        fc = json.load(open(fc_path))
    for domain in {d for _, _, _, d in factors}:
        fc[domain] = {}
    for name, cat, label, domain in factors:
        mode = 'overwrite' if '--force' in sys.argv else 'skip'
        fc[domain][name] = {'cat': cat, 'label': label, 'mode': mode}
    with open(fc_path, 'w') as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
    print(f'  → factors_config.json 已写入')

    # 写 config.json（基础设施，不含因子列表）
    old_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
    cfg = {}
    for k in ('tables', 'output_paths', 'key_cols', 'analysis_dir'):
        if k in old_cfg:
            cfg[k] = old_cfg[k]
    cfg['analysis'] = ['charts', 'ic', 'rr', 'sig']
    if '--force' in sys.argv:
        cfg['analysis_overwrite'] = ['charts', 'ic', 'rr', 'sig']
        print(f'  → 覆盖模式：因子值 + 分析将重算')
    cfg['sub_period'] = {'from_file': 'data/market_periods.json', 'groups': ['bull', 'bear', 'consolidate']}
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'  → config.json 已改写（基础设施）')

    # 跑 Pipeline
    print('\n=== 运行 Pipeline ===')
    from factor_workbench.pipeline import Pipeline
    p = Pipeline(CONFIG_PATH, backend='duckdb')
    try:
        p.run()
    finally:
        p.close()


if __name__ == '__main__':
    main()
