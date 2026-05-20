"""主入口。通过框架 pipeline 运行因子计算和分析。"""

import os
import sys

# 确保能找到 framework/
sys.path.insert(0, os.path.dirname(__file__))

from framework.pipeline import Pipeline


def main():
    pipeline = Pipeline('config/config.json', backend='duckdb')
    try:
        pipeline.run()
    finally:
        pipeline.close()


if __name__ == '__main__':
    main()
