"""Pipeline：统一调度入口。

配置驱动，按 domain 依次计算因子，再运行评价指标。
"""

import json
import os
import time
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

from .data_api import DataAPI
from .registry import get_factors, get_features, load_factor_modules
from .metric_runner import run_metrics
from ..metrics import chart_metric, ic_metric, rr_metric, sig_metric

def _try_read(path):
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _factor_worker(domain, name, backend, factor_dir='factors', tables=None):
    """进程池 worker：初始化 API → 运行因子 → 返回结果 DataFrame。"""
    from factor_workbench.engine.registry import load_factor_modules
    from factor_workbench.engine.data_api import DataAPI
    load_factor_modules(['factors', 'features'])
    factors = get_factors(domain=domain)
    factors.update(get_features(domain=domain))
    meta = factors.get(name)
    if meta is None:
        return name, None

    api = DataAPI(backend=backend, tables=tables)
    try:
        df = meta.fn(api)
        return name, df
    except Exception as e:
        return name, e
    finally:
        api.close()


class Pipeline:
    def __init__(self, config_path, backend='duckdb', load_analysis_data=None):
        self.cfg = json.load(open(config_path))
        self.backend = backend
        self.api = DataAPI(backend=backend, tables=self.cfg.get('tables'))
        self._load_data_fn = load_analysis_data
        load_factor_modules(['factors', 'features'])

    def run(self):
        """全流程入口。"""
        t0 = time.time()

        # 计算特征（存 feature_library）
        if os.path.exists('config/features_config.json'):
            for domain, factors in json.load(open('config/features_config.json')).items():
                self.cfg['output_paths'][domain] = self.cfg['feature_output_paths'][domain]
                print(f'\n=== {domain} 特征计算 ===')
                self._compute_domain(domain, factors)

        # 计算因子（存 factor_library）
        if os.path.exists('config/factors_config.json'):
            for domain, factors in json.load(open('config/factors_config.json')).items():
                pass  # output_paths[domain] 由 config 提供
                print(f'\n=== {domain} 因子计算 ===')
                self._compute_domain(domain, factors)

        # 分析
        if self.cfg.get('analysis'):
            print('\n=== 分析 ===')
            self._run_analysis()

        # 汇总
        print('\n=== 生成汇总表 ===')
        self._run_summary()

        print(f'\n全流程完成, 总耗时 {time.time()-t0:.1f}s')

    def _compute_domain(self, domain, selected):
        """计算一个 domain 的所有选中因子。增量 + 并行。"""
        key_cols = self.cfg['key_cols'][domain]
        output_path = self.cfg['output_paths'][domain]

        # 读已有数据
        existing = _try_read(output_path)
        if existing is not None:
            existing_cols = set(existing.columns)
        else:
            existing_cols = set()

        # 过滤出需要计算的（因子+特征）
        factors = get_factors(domain=domain)
        factors.update(get_features(domain=domain))
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

        fdir = self.cfg.get('factor_dir', 'factors')
        tbls = self.cfg.get('tables', {})
        if len(to_compute) == 1 or n_workers == 1:
            print(f'  [串行] {len(to_compute)} 个因子')
            for name in to_compute:
                r = _factor_worker(domain, name, self.backend, fdir, tbls)
                results[name] = r[1]
        else:
            print(f'  [并行] {len(to_compute)} 个因子, {n_workers} 进程')
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(_factor_worker, domain, name, self.backend, fdir, tbls): name
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
                for n, r in results.items():
                    if r is None:
                        print(f'  [{n}] 函数未找到')
                    elif isinstance(r, Exception):
                        print(f'  [{n}] 错误: {r}')
                    else:
                        print(f'  [{n}] 返回类型异常: {type(r).__name__}')
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
        """运行评价指标（直接调 @metric 函数）。"""
        analysis = self.cfg.get('analysis', [])
        if not analysis:
            return

        # 注册因子库/特征库表（刚算完的文件可能还没注册）
        for pkey in ('output_paths', 'feature_output_paths'):
            for domain, p in self.cfg.get(pkey, {}).items():
                pname = os.path.splitext(os.path.basename(p))[0]
                if pname not in self.cfg.get('tables', {}):
                    self.api.register_table(pname, p)

        fc_domains = list(json.load(open('config/factors_config.json')).keys()) if os.path.exists('config/factors_config.json') else ['industry', 'monthly']
        for factor_type in fc_domains:
            date_col = 'ym' if 'monthly' in str(factor_type) else 'trade_date'
            df = self._load_analysis_data(factor_type)
            if df is None:
                continue
            for name in analysis:
                t0 = time.time()
                print(f'\n=== {factor_type} {name} 分析 ===')
                run_metrics(self.cfg, factor_type, df, date_col=date_col, check_subdir=name)
                print(f'  [{name}] 耗时: {time.time()-t0:.1f}s')

    def _load_analysis_data(self, factor_type):
        """加载分析用的数据。支持外部自定义函数。"""
        if self._load_data_fn:
            return self._load_data_fn(self.api, factor_type)
        if factor_type == 'industry':
            df = self.api.table('industry_factors', columns=None)
            # 合并指数数据算前向收益
            idx = self.api.table('industry_daily', columns=['industry_code', 'trade_date', 'close'])
            idx = idx.rename(columns={'close': 'idx_close'})
            df = df.merge(idx, on=['industry_code', 'trade_date'], how='inner')
            df = df.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
            g = df.groupby('industry_code')['idx_close']
            for h in (1, 5, 10, 22):
                df[f'ret_T{h}'] = g.transform(lambda x: x.shift(-h) / x - 1)
            return df
        elif 'monthly' in str(factor_type):
            df = self.api.table('industry_monthly_factors', columns=None)
            if 'ym' not in df.columns:
                return None
            idx = self.api.table('industry_daily', columns=['industry_code', 'trade_date', 'close'])
            idx = idx.rename(columns={'close': 'idx_close'})
            idx = idx.sort_values(['industry_code', 'trade_date']).reset_index(drop=True)
            idx['ym'] = idx['trade_date'].str[:6]
            monthly = idx.groupby(['industry_code', 'ym']).tail(1).copy()
            monthly['ret_T1'] = monthly.groupby('industry_code')['idx_close'].transform(
                lambda x: x.shift(-1) / x - 1)
            df = df.merge(monthly[['industry_code', 'ym', 'ret_T1']], on=['industry_code', 'ym'], how='left')
            return df
        elif factor_type == 'stock':
            if 'stock_factors' not in self.cfg.get('tables', {}):
                return None
            df = self.api.table('stock_factors', columns=None)
            if df.empty:
                return None
            idx = self.api.table('stock_daily', columns=['stock_code', 'trade_date', 'close'])
            idx = idx.rename(columns={'close': 'idx_close'})
            df = df.merge(idx, on=['stock_code', 'trade_date'], how='inner')
            df = df.sort_values(['stock_code', 'trade_date']).reset_index(drop=True)
            g = df.groupby('stock_code')['idx_close']
            for h in (1, 5, 10, 22):
                df[f'ret_T{h}'] = g.transform(lambda x: x.shift(-h) / x - 1)
            return df
        return None

    def _run_summary(self):
        """生成汇总表。"""
        from factor_workbench.analysis.summarize_results import main as summary_main
        summary_main()

    def close(self):
        self.api.close()
