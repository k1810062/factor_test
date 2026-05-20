"""Pipeline：统一调度入口。

配置驱动，按 domain 依次计算因子，再运行评价指标。
"""

import json
import os
import time
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

from framework.data_api import DataAPI
from framework.registry import get_factors, get_metrics
import factors.stock_factors
import factors.industry_factors
import factors.monthly_factors

# 各 domain 的输出路径
OUTPUT_PATHS = {
    'stock':    'output/data_processed/factor_stock.parquet',
    'industry': 'output/data_processed/industry_daily_ratio.parquet',
    'monthly':  'output/data_processed/industry_monthly_ratio.parquet',
}

# 各 domain 的 key 列
KEY_COLS = {
    'stock':    ['STOCK_CODE', 'TRADE_DATE'],
    'industry': ['industry_code', 'TRADE_DATE'],
    'monthly':  ['industry_code', 'ym'],
}


def _try_read(path):
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _factor_worker(domain, name, backend):
    """进程池 worker：初始化 API → 运行因子 → 返回结果 DataFrame。"""
    import importlib
    importlib.import_module(f'factors.{domain}_factors')
    from framework.registry import get_factors
    from framework.data_api import DataAPI

    factors = get_factors(domain=domain)
    meta = factors.get(name)
    if meta is None:
        return name, None

    api = DataAPI(backend=backend)
    try:
        df = meta.fn(api)
        return name, df
    except Exception as e:
        return name, e
    finally:
        api.close()


class Pipeline:
    def __init__(self, config_path, backend='duckdb'):
        self.cfg = json.load(open(config_path))
        self.backend = backend
        self.api = DataAPI(backend=backend)

    def run(self):
        """全流程入口。"""
        t0 = time.time()

        for domain in ('stock', 'industry', 'monthly'):
            selected = self.cfg.get(domain, {})
            if not selected:
                continue
            print(f'\n=== {domain} 因子计算 ===')
            self._compute_domain(domain, selected)

        # 分析（复用现有分析流程）
        if self.cfg.get('analysis'):
            print('\n=== 分析 ===')
            self._run_analysis()

        # 汇总
        print('\n=== 生成汇总表 ===')
        self._run_summary()

        print(f'\n全流程完成, 总耗时 {time.time()-t0:.1f}s')

    def _compute_domain(self, domain, selected):
        """计算一个 domain 的所有选中因子。增量 + 并行。"""
        key_cols = KEY_COLS[domain]
        output_path = OUTPUT_PATHS[domain]

        # 读已有数据
        existing = _try_read(output_path)
        if existing is not None:
            existing_cols = set(existing.columns)
        else:
            existing_cols = set()

        # 过滤出需要计算的
        factors = get_factors(domain=domain)
        to_compute = []
        overwrite_names = set()

        for name, meta in factors.items():
            if name not in selected:
                continue
            mode = selected.get(name, {}).get('mode', 'skip')
            if mode == 'overwrite' and name in existing_cols:
                overwrite_names.add(name)
                continue  # will be handled below
            if name not in existing_cols:
                to_compute.append(name)

        if overwrite_names:
            if existing is not None:
                existing = existing.drop(columns=[c for c in overwrite_names if c in existing.columns])
                existing_cols = set(existing.columns)
            for name in overwrite_names:
                print(f'  [{name}] overwrite')
                to_compute.append(name)

        if not to_compute:
            print('  [跳过] 全部已存在')
            return

        print(f'  需计算: {to_compute} ({len(to_compute)} 个)')

        # 并行计算
        t1 = time.time()
        results = {}
        n_workers = min(os.cpu_count() or 4, len(to_compute))

        if len(to_compute) == 1 or n_workers == 1:
            # 串行
            for name in to_compute:
                r = _factor_worker(domain, name, self.backend)
                results[name] = r[1]
        else:
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(_factor_worker, domain, name, self.backend): name
                    for name in to_compute
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        _, result = future.result()
                        results[name] = result
                    except Exception as e:
                        print(f'  [{name}] 失败: {e}')

        # 合并结果
        if existing is None:
            # 首次：从已有结果中取 key 列
            first_result = next((v for v in results.values() if isinstance(v, pd.DataFrame) and v is not None), None)
            if first_result is None:
                print('  无有效结果')
                return
            result_df = first_result[key_cols].copy()
        else:
            result_df = existing.copy()

        for name in to_compute:
            r = results.get(name)
            if r is None:
                print(f'  [{name}] 无结果')
                continue
            if isinstance(r, Exception):
                print(f'  [{name}] 错误: {r}')
                continue
            if name in result_df.columns:
                result_df = result_df.drop(columns=[name])
            result_df = result_df.merge(r, on=key_cols, how='left')
            cols = [c for c in result_df.columns if c not in key_cols]
            print(f'  [{name}] done ({time.time()-t1:.1f}s)')

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result_df.to_parquet(output_path, index=False)
        print(f'  → 保存 {output_path} ({len(result_df)} 行, '
              f'{len([c for c in result_df.columns if c not in key_cols])} 个因子)')

    def _run_analysis(self):
        """运行评价指标（暂用现有分析流程）。"""
        analysis = self.cfg.get('analysis', [])
        if not analysis:
            return
        base = os.path.dirname(os.path.dirname(__file__))
        import runpy
        runpy.run_path(f'{base}/analysis/analyze_all.py', run_name='__main__')

    def _run_summary(self):
        """生成汇总表（暂用现有汇总脚本）。"""
        base = os.path.dirname(os.path.dirname(__file__))
        import runpy
        runpy.run_path(f'{base}/analysis/summarize_results.py', run_name='__main__')

    def close(self):
        self.api.close()
