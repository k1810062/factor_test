"""Registry：@factor / @metric 装饰器 + 自动注册。

用法：
    @factor(name="up_ratio", category="pv", label="上涨家数占比", domain="industry")
    def up_ratio(api):
        ...

    @metric(name="ic", label="Rank IC分析")
    def ic_metric(api, df, factor_name):
        ...
"""

import os
from dataclasses import dataclass


@dataclass
class FactorMeta:
    name: str
    fn: callable
    category: str
    label: str
    domain: str


@dataclass
class FeatureMeta:
    name: str
    fn: callable
    domain: str


@dataclass
class MetricMeta:
    name: str
    fn: callable
    label: str


_FACTORS: dict[str, FactorMeta] = {}
_FEATURES: dict[str, FeatureMeta] = {}
_METRICS: dict[str, MetricMeta] = {}


def factor(name, category, label, domain='stock'):
    """注册一个因子（计算+分析）。"""
    def wrapper(fn):
        _FACTORS[f'{domain}:{name}'] = FactorMeta(
            name=name, fn=fn, category=category, label=label, domain=domain,
        )
        return fn
    return wrapper


def feature(name, domain='stock'):
    """注册一个特征（中间量，只计算不分析）。"""
    def wrapper(fn):
        _FEATURES[f'{domain}:{name}'] = FeatureMeta(
            name=name, fn=fn, domain=domain,
        )
        return fn
    return wrapper


def load_factor_modules(factor_dirs=None):
    """扫描目录下的所有 .py 文件并导入，触发 @factor/@metric 注册。"""
    if factor_dirs is None:
        factor_dirs = ['factors']
    elif isinstance(factor_dirs, str):
        factor_dirs = [factor_dirs]
    for factor_dir in factor_dirs:
        if not os.path.isdir(factor_dir):
            os.makedirs(factor_dir)
        import pandas as pd, numpy as np
        for f in sorted(os.listdir(factor_dir)):
            if not f.endswith('.py') or f.startswith('_'):
                continue
            path = os.path.join(factor_dir, f)
            try:
                exec(compile(open(path).read(), path, 'exec'), {
                    'factor': factor, 'feature': feature,
                    'pd': pd, 'np': np,
                    '__builtins__': __builtins__,
                })
            except Exception as e:
                print(f'  [registry] 加载 {f} 失败: {e}')


def metric(name, label):
    """注册一个评价指标。"""
    def wrapper(fn):
        _METRICS[name] = MetricMeta(name=name, fn=fn, label=label)
        return fn
    return wrapper


def get_factors(domain=None, category=None):
    """查询已注册的因子。"""
    result = {}
    for key, meta in _FACTORS.items():
        if domain and meta.domain != domain:
            continue
        if category and meta.category != category:
            continue
        result[meta.name] = meta
    return result


def get_features(domain=None):
    """查询已注册的特征（中间量）。"""
    result = {}
    for key, meta in _FEATURES.items():
        if domain and meta.domain != domain:
            continue
        result[meta.name] = meta
    return result


def get_metrics():
    """查询已注册的评价指标。"""
    return dict(_METRICS)
