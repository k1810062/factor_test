"""DataAPI：统一数据访问层。

因子函数不写文件路径，只认表名。通过 api.table() 取 DataFrame，
或 api.query() 写 SQL。后端在 duckdb 和 parquet 之间切换不影响调用方。
"""

import pandas as pd
import os

# 默认表名 → 文件路径映射（可被项目配置覆盖）
DEFAULT_TABLES = {
    'stock_base':         'data/stock_base.parquet',
    'swi_daily':          'data/SWI_daily.parquet',
    'etf_daily':          'data/etf_daily.parquet',
    'factor_stock':       'output/data_processed/factor_stock.parquet',
    'industry_daily':     'output/data_processed/industry_daily_ratio.parquet',
    'industry_daily_z':   'output/data_processed/industry_daily_ratio_z.parquet',
    'industry_monthly':   'output/data_processed/industry_monthly_ratio.parquet',
}


class DataAPI:
    def __init__(self, backend='duckdb', tables=None):
        self._backend = backend
        self._tables = dict(DEFAULT_TABLES)
        if tables:
            self._tables.update(tables)
        self._conn = None
        self._cache = {}

        if backend == 'duckdb':
            import duckdb
            self._conn = duckdb.connect()
            for name, path in self._tables.items():
                if os.path.exists(path):
                    safe = name.replace('-', '_').replace('.', '_')
                    try:
                        self._conn.execute(
                            f"CREATE OR REPLACE VIEW \"{safe}\" AS "
                            f"SELECT * FROM read_parquet('{os.path.abspath(path)}')"
                        )
                    except Exception as e:
                        print(f'  [DataAPI] 注册表 {name} 失败: {e}')

    def _resolve(self, name):
        safe = name.replace('-', '_').replace('.', '_')
        if safe not in self._tables:
            raise KeyError(f"未知表名: {name}，已知: {list(self._tables.keys())}")
        return safe

    def query(self, sql):
        """执行 SQL，返回 DataFrame。只在 duckdb 后端可用。"""
        if self._backend != 'duckdb':
            raise RuntimeError("query() 需要 duckdb 后端")
        return self._conn.sql(sql).df()

    def table(self, name, columns=None):
        """取一张表为 DataFrame。每次重新创建 view 以同步 schema。"""
        safe = self._resolve(name)
        path = self._tables[safe]

        if self._backend == 'duckdb':
            if os.path.exists(path):
                self._conn.execute(
                    f'CREATE OR REPLACE VIEW "{safe}" AS '
                    f"SELECT * FROM read_parquet('{os.path.abspath(path)}')"
                )
            cols = ', '.join(f'"{c}"' for c in columns) if columns else '*'
            return self._conn.sql(f'SELECT {cols} FROM "{safe}"').df()
        else:
            return pd.read_parquet(path, columns=columns)

    def register_table(self, name, path):
        """运行时注册新表。"""
        self._tables[name] = path
        if self._backend == 'duckdb':
            safe = name.replace('-', '_').replace('.', '_')
            if os.path.exists(path):
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW \"{safe}\" AS "
                    f"SELECT * FROM read_parquet('{os.path.abspath(path)}')"
                )

    def close(self):
        if self._conn:
            self._conn.close()
