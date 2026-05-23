"""
草稿因子 → 追加到因子库 → 改配置 → 跑 pipeline。

用法：
    python3 -m factor_workbench.scratch my_factor.py
    python3 -m factor_workbench.scratch --force my_factor.py
"""

import sys, os, json, re

# 首次运行自动生成 config
from .auto_config import generate_config
generate_config()

CONFIG_PATH = 'config/config.json'
_CFG = json.load(open(CONFIG_PATH))
_FACTOR_DIR = _CFG.get('factor_dir', 'factors')

FACTOR_FILES = {
    'stock':    f'{_FACTOR_DIR}/stock_features.py',
    'industry': f'{_FACTOR_DIR}/industry_factors.py',
    'monthly':  f'{_FACTOR_DIR}/monthly_factors.py',
}

FEATURE_FILES = {
    'stock':    f'{_FACTOR_DIR}/stock_features.py',
}


def _extract_func(code, name, kind='factor'):
    """从多函数代码块中提取指定名称的函数。"""
    i = code.find(f"@{kind}(name='{name}'")
    if i < 0:
        return code.strip()
    nxt = len(code)
    for k in ('factor', 'feature', 'metric'):
        p = code.find(f'\n@{k}(', i + 1)
        if 0 < p < nxt:
            nxt = p
    return code[i:nxt].strip()


def main():
    path = sys.argv[2] if '--force' in sys.argv else sys.argv[1]
    code = open(path).read()

    factors = re.findall(
        r"@factor\(name='(\w+)',\s*category='(\w+)',\s*label='(.+?)',\s*domain='(\w+)'",
        code)
    features = re.findall(
        r"@feature\(name='(\w+)',\s*domain='(\w+)'",
        code)

    if not factors and not features:
        print('错误：未识别到 @factor 或 @feature 装饰器')
        print('文件内容:')
        print(code[:500])
        sys.exit(1)

    # 写配置
    fc_path, feat_path = 'config/factors_config.json', 'config/features_config.json'
    fc, feat = {}, {}
    ow = 'overwrite' if '--force' in sys.argv else 'skip'
    for name, cat, label, domain in factors:
        fc.setdefault(domain, {})[name] = {'cat': cat, 'label': label, 'mode': ow}
    for name, domain in features:
        feat.setdefault(domain, {})[name] = {'mode': ow}
    json.dump(fc, open(fc_path, 'w'), ensure_ascii=False, indent=2)
    json.dump(feat, open(feat_path, 'w'), ensure_ascii=False, indent=2)
    if fc: print(f'  → factors_config.json（{sum(len(v) for v in fc.values())} 个因子）')
    if feat: print(f'  → features_config.json（{sum(len(v) for v in feat.values())} 个特征）')

    # 写 config.json（基础设施）
    old_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
    cfg = {}
    for k in ('tables', 'output_paths', 'key_cols', 'analysis_dir'):
        if k in old_cfg:
            cfg[k] = old_cfg[k]
    cfg['analysis'] = ['charts', 'ic', 'rr', 'sig']
    if '--force' in sys.argv:
        cfg['analysis_overwrite'] = ['charts', 'ic', 'rr', 'sig']
        print('  → 覆盖模式：因子值 + 分析将重算')
    cfg['sub_period'] = {'from_file': 'data/market_periods.json', 'groups': ['bull', 'bear', 'consolidate']}
    json.dump(cfg, open(CONFIG_PATH, 'w'), ensure_ascii=False, indent=2)
    print('  → config.json 已改写（基础设施）')

    # 跑 Pipeline（先初始化再注册，防止文件中的旧版覆盖新版）
    print('\n=== 运行 Pipeline ===')
    from .pipeline import Pipeline
    from .registry import factor, feature
    p = Pipeline(CONFIG_PATH, backend='duckdb')
    exec(compile(open(path).read(), path, 'exec'), {'factor': factor, 'feature': feature})

    success = False
    try:
        p.run()
        success = True
    finally:
        p.close()

    # pipeline 成功后写入因子/特征文件
    if success:
        for name, cat, label, domain in factors:
            target = FACTOR_FILES.get(domain, FACTOR_FILES['industry'])
            existing = open(target).read()
            if f"@factor(name='{name}'" in existing:
                print(f'  [{name}] 已存在，跳过')
                continue
            func_code = _extract_func(code, name, 'factor')
            with open(target, 'a') as f:
                f.write('\n\n# ─── 新增因子 ───\n' + func_code + '\n')
            print(f'  [{name}] → 已加入因子库')
        for name, domain in features:
            target = FEATURE_FILES.get(domain, list(FEATURE_FILES.values())[0])
            existing = open(target).read()
            if f"@feature(name='{name}'" in existing:
                print(f'  [{name}] 已存在，跳过')
                continue
            func_code = _extract_func(code, name, 'feature')
            with open(target, 'a') as f:
                f.write('\n\n# ─── 新增特征 ───\n' + func_code + '\n')
            print(f'  [{name}] → 已加入特征库')


def __main():
    main()

if __name__ == "__main__":
    __main()
