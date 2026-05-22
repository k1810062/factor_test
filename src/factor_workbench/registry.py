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
    domain: str          # 'stock' | 'industry' | 'monthly'
    published: bool = True   # False = 中间量，不在搜索/列表展示


@dataclass
class MetricMeta:
    name: str
    fn: callable
    label: str


_FACTORS: dict[str, FactorMeta] = {}
_METRICS: dict[str, MetricMeta] = {}


def factor(name, category, label, domain='stock', published=True):
    """注册一个因子。published=False 表示中间量，不在搜索/列表展示。"""
    def wrapper(fn):
        key = f'{domain}:{name}'
        _FACTORS[key] = FactorMeta(
            name=name, fn=fn, category=category, label=label,
            domain=domain, published=published,
        )
        return fn
    return wrapper


def load_factor_modules(factor_dir='factors'):
    """扫描目录下的所有 .py 文件并导入，触发 @factor/@metric 注册。"""
    if not os.path.isdir(factor_dir):
        print(f'  [registry] 因子目录不存在: {factor_dir}')
        return
    import importlib.util
    for f in sorted(os.listdir(factor_dir)):
        if not f.endswith('.py') or f.startswith('_'):
            continue
        path = os.path.join(factor_dir, f)
        name = f[:-3]
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
        except Exception as e:
            print(f'  [registry] 加载 {f} 失败: {e}')


def metric(name, label):
    """注册一个评价指标。"""
    def wrapper(fn):
        _METRICS[name] = MetricMeta(name=name, fn=fn, label=label)
        return fn
    return wrapper


def get_factors(domain=None, category=None, published=None):
    """查询已注册的因子，可按 domain / category / published 过滤。"""
    result = {}
    for key, meta in _FACTORS.items():
        if domain and meta.domain != domain:
            continue
        if category and meta.category != category:
            continue
        if published is not None and meta.published != published:
            continue
        result[meta.name] = meta
    return result


def get_metrics():
    """查询已注册的评价指标。"""
    return dict(_METRICS)
