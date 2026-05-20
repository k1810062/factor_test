"""Registry：@factor / @metric 装饰器 + 自动注册。

用法：
    @factor(name="up_ratio", category="pv", label="上涨家数占比", domain="industry")
    def up_ratio(api):
        ...

    @metric(name="ic", label="Rank IC分析")
    def ic_metric(api, df, factor_name):
        ...
"""

from dataclasses import dataclass, field


@dataclass
class FactorMeta:
    name: str
    fn: callable
    category: str
    label: str
    domain: str          # 'stock' | 'industry' | 'monthly'


@dataclass
class MetricMeta:
    name: str
    fn: callable
    label: str


_FACTORS: dict[str, FactorMeta] = {}
_METRICS: dict[str, MetricMeta] = {}


def factor(name, category, label, domain='stock'):
    """注册一个因子。允许不同 domain 使用同名。"""
    def wrapper(fn):
        key = f'{domain}:{name}'
        _FACTORS[key] = FactorMeta(
            name=name, fn=fn, category=category, label=label, domain=domain,
        )
        return fn
    return wrapper


def metric(name, label):
    """注册一个评价指标。"""
    def wrapper(fn):
        _METRICS[name] = MetricMeta(name=name, fn=fn, label=label)
        return fn
    return wrapper


def get_factors(domain=None, category=None):
    """查询已注册的因子，可按 domain 和 category 过滤。"""
    result = {}
    for key, meta in _FACTORS.items():
        if domain and meta.domain != domain:
            continue
        if category and meta.category != category:
            continue
        result[meta.name] = meta
    return result


def get_metrics():
    """查询已注册的评价指标。"""
    return dict(_METRICS)
