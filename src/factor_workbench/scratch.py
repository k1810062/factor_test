"""
草稿因子 → 追加到因子库 → 改配置 → 跑 pipeline。

用法：
    python3 -m factor_workbench.scratch my_factor.py
    python3 -m factor_workbench.scratch --force my_factor.py
"""

import sys, os, json, re
from pathlib import Path

# 切到项目根目录
os.chdir(str(Path(__file__).resolve().parent.parent.parent))

# 首次运行自动生成 config
from .analysis.auto_config import generate_config
generate_config()

CONFIG_PATH = 'config/config.json'
_CFG = json.load(open(CONFIG_PATH))


def _target(domain):
    return f'factors/{domain}_factors.py'


def _extract_func(code, name, kind='factor'):
    """从多函数代码块中提取指定名称的函数。"""
    i = code.find(f"@{kind}(name='{name}'")
    if i < 0:
        return code.strip()
    nxt = len(code)
    for k in ('factor',):
        p = code.find(f'\n@{k}(', i + 1)
        if 0 < p < nxt:
            nxt = p
    return code[i:nxt].strip()


def main():
    path = sys.argv[2] if '--force' in sys.argv else sys.argv[1]
    code = open(path).read()

    import ast
    tree = ast.parse(code)
    factors = []

    def _get_kw(node, *keys):
        for kw in node.keywords:
            if kw.arg in keys:
                return ast.literal_eval(kw.value)
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.decorator_list:
            continue
        dec = node.decorator_list[0]
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Name):
            continue
        if dec.func.id != 'factor':
            continue
        name = _get_kw(dec, 'name')
        domain = _get_kw(dec, 'domain')
        if not name or not domain:
            continue
        _freq = _get_kw(dec, 'freq') or 'daily'

    if not factors:
        print('错误：未识别到 @factor 装饰器')
        print('文件内容:')
        print(code[:500])
        sys.exit(1)

    # 写配置
    fc_path = 'config/factors_config.json'
    fc = {}
    ow = 'overwrite' if '--force' in sys.argv else 'skip'
    print(f'  → 模式: {ow}{" (--force)" if "--force" in sys.argv else ""}')
    for name, cat, label, domain, freq in factors:
        fc.setdefault(domain, {})[name] = {'cat': cat, 'label': label, 'mode': ow, 'freq': freq}
    json.dump(fc, open(fc_path, 'w'), ensure_ascii=False, indent=2)
    if fc:
        print(f'  → factors_config.json（{sum(len(v) for v in fc.values())} 个因子）')

    # 写 config.json（基础设施）
    old_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
    cfg = {}
    for k in ('tables', 'output_paths', 'key_cols', 'analysis_dir'):
        if k in old_cfg:
            cfg[k] = old_cfg[k]
    cfg['analysis'] = ['charts', 'ic', 'rr', 'sig', 'decile', 'ts']
    if '--force' in sys.argv:
        cfg['analysis_overwrite'] = ['ic', 'decile', 'sig', 'rr', 'ts']
        print('  → 覆盖模式：因子值 + 分析将重算')
    cfg['sub_period'] = {'from_file': 'data/market_periods.json', 'groups': ['bull', 'bear', 'consolidate']}
    json.dump(cfg, open(CONFIG_PATH, 'w'), ensure_ascii=False, indent=2)
    print('  → config.json 已改写（基础设施）')

    # 跑 Pipeline
    print('\n=== 运行 Pipeline ===')
    from .engine.pipeline import Pipeline
    from .engine.registry import factor
    p = Pipeline(CONFIG_PATH, backend='duckdb')
    exec(compile(open(path).read(), path, 'exec'), {'factor': factor})

    success = False
    try:
        p.run()
        success = True
    finally:
        p.close()

    # pipeline 成功后写入因子文件
    if success:
        for name, cat, label, domain, _freq in factors:
            target = _target(domain)
            if not os.path.exists(target):
                open(target, 'w').write(f'# {domain} 因子\n')
                print(f'  [创建] {target}')
            existing = open(target).read()
            if f"@factor(name='{name}'" in existing:
                print(f'  [{name}] 已存在，跳过')
                continue
            func_code = _extract_func(code, name, 'factor')
            with open(target, 'a') as f:
                f.write('\n\n# ─── 新增因子 ───\n' + func_code + '\n')
            print(f'  [{name}] → 已加入因子库')


def __main():
    main()

if __name__ == "__main__":
    __main()
