"""扫描 parquet，自动生成数据字典 data_dictionary.json。

用法：
    python3 scan_schema.py

已有描述不会被覆盖（仅新字段补充默认描述）。
"""

import json
import os
import re
from pathlib import Path

import duckdb

# DATA_DIR
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
_DATA_DIR = os.environ.get('FACTOR_DATA', os.path.join(os.path.dirname(_PROJECT_ROOT), 'factor_data'))

# 表名 → 中文描述（按命名前缀自动匹配）
_TABLE_PREFIX = {
    'stock_': '个股',
    'industry_': '行业指数',
    'etf_': 'ETF',
}

_DEFAULT_DESCRIPTIONS = {
    'stock_code': '股票代码',
    'trade_date': '交易日',
    'industry_code': '行业代码',
    'close': '收盘价',
    'open': '开盘价',
    'vol': '成交量（股）',
    'amount': '成交金额（元）',
    'turn': '换手率',
    'mv': '总市值',
    'pe_ttm': '滚动市盈率',
    'pb': '市净率',
    'inflow_rate': '资金流入率',
    'borrow_buy': '融资买入额',
    'borrow_repay': '融资偿还额',
    'roe_ttm': '净资产收益率',
    'val_mv': '流通市值',
    'net_asset_value': '净资产',
    'rating_grade': '分析师评级',
    'ym': '年月',
    'etf_code': 'ETF代码',
    'industry': '行业名称',
    'n': '上市天数',
}


def _auto_description(name: str) -> str:
    if name in _DEFAULT_DESCRIPTIONS:
        return _DEFAULT_DESCRIPTIONS[name]
    # 用关键词推测含义
    kw = {
        'ratio': '占比', 'rate': '率', 'avg': '均值', 'pctl': '分位',
        'ret': '收益率', 'mom': '动量', 'divg': '背离', 'spread': '差',
        'bull': '多头', 'bear': '空头', 'etf': 'ETF', 'inflow': '资金流入',
        'margin': '融资', 'strong': '强势', 'tech': '技术', 'sync': '同步',
        'break': '突破', 'improve': '改善', 'diverge': '背离',
    }
    matched = [v for k, v in kw.items() if k in name.lower()]
    return ' '.join(matched) if matched else name


def main(config_path=None,
         output_path=None):
    if config_path is None:
        config_path = os.path.join(_DATA_DIR, 'config/config.json')
    if output_path is None:
        output_path = os.path.join(_DATA_DIR, 'config/data_dictionary.json')
    with open(config_path) as f:
        config = json.load(f)

    tables_cfg = config.get('tables', {})

    # 排除因子库表（只留原始数据和特征库）
    tables_cfg = {k: v for k, v in tables_cfg.items()
                  if 'factor_library' not in v}

    # 读已有字典，保留人工描述
    existing = {}
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
    existing_fields = {}
    existing_table_desc = {}
    for t in existing.get('tables', []):
        for fd in t.get('fields', []):
            existing_fields[f"{t['name']}.{fd['name']}"] = fd.get('description', '')
        if 'description' in t:
            existing_table_desc[t['name']] = t['description']

    def _table_desc(name: str) -> str:
        if name in existing_table_desc:
            return existing_table_desc[name]
        for prefix, label in _TABLE_PREFIX.items():
            if name.startswith(prefix):
                return f'{label}的数据' if 'feature' in name else f'{label}行情'
        return name

    new_tables = []
    for name, path in tables_cfg.items():
        if not os.path.exists(path):
            continue
        conn = duckdb.connect()
        conn.execute(f"CREATE VIEW _v AS SELECT * FROM read_parquet('{path}')")
        schema = conn.sql('DESCRIBE _v').df()
        conn.close()

        fields = []
        for _, row in schema.iterrows():
            fname = row['column_name']
            key = f'{name}.{fname}'
            desc = existing_fields.get(key, '') or _auto_description(fname)
            fields.append({'name': fname, 'type': row['column_type'], 'description': desc})

        new_tables.append({'name': name, 'description': _table_desc(name), 'fields': fields})

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'tables': new_tables}, f, ensure_ascii=False, indent=2)

    total = sum(len(t['fields']) for t in new_tables)
    print(f'[scan_schema] {len(new_tables)} 张表, {total} 个字段 → {output_path}')


if __name__ == '__main__':
    main()
