"""主入口：全量跑 pipeline。

用法：python3 -m factor_workbench.run
"""
from .analysis.auto_config import generate_config
from .engine.pipeline import Pipeline


def main():
    generate_config()
    p = Pipeline('config/config.json', backend='duckdb')
    try:
        p.run()
    finally:
        p.close()


if __name__ == '__main__':
    main()
