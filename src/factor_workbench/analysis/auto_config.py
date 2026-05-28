"""扫描 parquet 文件，注册表映射，保证 domain 配置存在。

自动发现只做两件事：
1. 扫 data/ 和 output/feature_library/ → 注册到 tables
2. 保证因子库 3 个 domain 的 key_cols 和 output_paths 有默认值
"""

import os, json, glob


# 因子库 domain 定义
DOMAINS = {
    'stock':            {'key': ['stock_code', 'trade_date'],   'path': 'output/factor_library/stock_factors.parquet',
                         'analysis_dir': 'output/analysis/stock'},
    'industry':         {'key': ['industry_code', 'trade_date'], 'path': 'output/factor_library/industry_factors.parquet',
                         'analysis_dir': 'output/analysis/industry'},
}

def _scan_parquets(dirs):
    """扫描目录下的 parquet，返回 {表名: 路径}。"""
    tables = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(f'{d}/*.parquet')):
            name = os.path.splitext(os.path.basename(f))[0].lower()
            tables[name] = os.path.abspath(f)
    return tables


def generate_config(config_path='config/config.json'):
    """扫描 parquet 注册到 tables，保证 domain 配置存在。"""
    tables = _scan_parquets(['data', 'output/factor_library'])

    cfg = {}
    if os.path.exists(config_path):
        cfg = json.load(open(config_path))

    # 表映射直接用扫描结果（文件名变则路径自动更新）
    cfg['tables'] = tables

    # 保证因子库 domain 配置存在
    for d, info in DOMAINS.items():
        cfg.setdefault('key_cols', {}).setdefault(d, info['key'])
        cfg.setdefault('output_paths', {}).setdefault(d, info['path'])

    # 每个 domain 独立分析目录
    if not isinstance(cfg.get('analysis_dir'), dict):
        cfg['analysis_dir'] = {}
    for d, info in DOMAINS.items():
        cfg['analysis_dir'].setdefault(d, info['analysis_dir'])

    cfg.setdefault('analysis', ['charts', 'ic', 'rr', 'sig'])
    cfg.setdefault('sub_period', {
        'from_file': 'data/market_periods.json',
        'groups': ['bull', 'bear', 'consolidate'],
    })

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    json.dump(cfg, open(config_path, 'w'), ensure_ascii=False, indent=2)
    print(f'[auto_config] 已更新 {config_path}')
