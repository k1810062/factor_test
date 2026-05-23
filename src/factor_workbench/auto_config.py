"""自动扫描 parquet 文件，推断表映射和 key 列，生成默认配置。"""

import os, json, glob
import pandas as pd

# key 列命名 → domain 推断规则
KEY_PATTERNS = [
    (['industry_code', 'ym'], 'monthly', ['industry_code', 'ym']),
    (['stock_code', 'trade_date'], 'stock', ['stock_code', 'trade_date']),
    (['industry_code', 'trade_date'], 'industry', ['industry_code', 'trade_date']),
]

DEFAULT_OUTPUT_PATHS = {
    'stock':    'output/factor_library/stock/daily.parquet',
    'industry': 'output/factor_library/industry/daily.parquet',
    'monthly':  'output/factor_library/industry/monthly.parquet',
}

DEFAULT_KEY_COLS = {
    'stock':    ['stock_code', 'trade_date'],
    'industry': ['industry_code', 'trade_date'],
    'monthly':  ['industry_code', 'ym'],
}


def _scan_parquets(dirs):
    """递归扫描目录下的 parquet，返回 {表名: 路径}。"""
    result = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                if not f.endswith('.parquet'):
                    continue
                name = os.path.splitext(f)[0].lower().replace('-', '_')
                rel = os.path.relpath(os.path.join(root, f), os.path.dirname(d))
                path_key = os.path.splitext(rel)[0].replace('/', '_').lower()
                result[name] = os.path.abspath(os.path.join(root, f))
    return result


def _infer_domain(cols):
    """根据列名推断 domain 和 key 列。"""
    for required, domain, key_cols in KEY_PATTERNS:
        if all(c in cols for c in required):
            return domain, key_cols
    return None, None


def discover(scan_dirs=None):
    """扫描 parquet 目录，返回 (tables, domains_found)。

    scan_dirs: 默认 ['data', 'output/data_processed']
    """
    if scan_dirs is None:
        scan_dirs = ['data']

    tables = _scan_parquets(scan_dirs)

    domains_found = {}
    for name, path in tables.items():
        try:
            cols = list(pd.read_parquet(path).head(0).columns)
        except Exception:
            continue
        domain, key_cols = _infer_domain(cols)
        if domain:
            domains_found[domain] = key_cols

    return tables, domains_found


def generate_config(scan_dirs=None, config_path='config/config.json'):
    """自动生成或更新 config.json。保留已有配置，补充新发现的表。"""
    tables, domains = discover(scan_dirs)

    # 读已有配置
    cfg = {}
    if os.path.exists(config_path):
        cfg = json.load(open(config_path))

    # 合并表（新发现的追加，不覆盖已有的）
    existing_tables = cfg.get('tables', {})
    for name, path in tables.items():
        if name not in existing_tables:
            existing_tables[name] = path
    cfg['tables'] = existing_tables

    # 补全 key_cols 和 output_paths
    for domain, key_cols in domains.items():
        cfg.setdefault('key_cols', {}).setdefault(domain, key_cols)
        if domain in DEFAULT_OUTPUT_PATHS:
            cfg.setdefault('output_paths', {}).setdefault(domain, DEFAULT_OUTPUT_PATHS[domain])

    # 默认值
    for d in ('stock', 'industry', 'monthly'):
        if d not in cfg.get('output_paths', {}):
            cfg.setdefault('output_paths', {})[d] = DEFAULT_OUTPUT_PATHS[d]
            cfg.setdefault('key_cols', {})[d] = DEFAULT_KEY_COLS[d]
    cfg.setdefault('analysis_dir', 'output/factor_analysis')
    cfg.setdefault('analysis', ['charts', 'ic', 'rr', 'sig'])
    cfg.setdefault('sub_period', {
        'from_file': 'data/market_periods.json',
        'groups': ['bull', 'bear', 'consolidate'],
    })

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'[auto_config] 已更新 {config_path}')
    return True
