"""DataAPI：统一数据访问层。

因子函数不写文件路径，只认表名。通过 api.table() 取 DataFrame，
或 api.query() 写 SQL。后端在 duckdb 和 parquet 之间切换不影响调用方。
"""

import pandas as pd
import os


class DataAPI:
    def __init__(self, backend='duckdb', tables=None):
        self._backend = backend
        self._tables = dict(tables) if tables else {}
        self._conn = None

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

    def _safe(self, name):
        """返回 DuckDB 兼容的视图名。"""
        return name.replace('-', '_').replace('.', '_')

    def query(self, sql):
        """执行 SQL，返回 DataFrame。只在 duckdb 后端可用。"""
        if self._backend != 'duckdb':
            raise RuntimeError("query() 需要 duckdb 后端")
        return self._conn.sql(sql).df()

    def table(self, name, columns=None):
        """取一张表为 DataFrame。重新创建 view 以同步 parquet 变更。"""
        if name not in self._tables:
            raise KeyError(f"未知表名: {name}，已知: {list(self._tables.keys())}")
        path = self._tables[name]
        safe = self._safe(name)

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
            safe = self._safe(name)
            if os.path.exists(path):
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW \"{safe}\" AS "
                    f"SELECT * FROM read_parquet('{os.path.abspath(path)}')"
                )

    def close(self):
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
