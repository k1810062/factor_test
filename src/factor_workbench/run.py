"""主入口：全量跑 pipeline。

用法：python3 -m factor_workbench.run
"""
from .pipeline import Pipeline


def main():
    p = Pipeline('config/config.json', backend='duckdb')
    try:
        p.run()
    finally:
        p.close()
