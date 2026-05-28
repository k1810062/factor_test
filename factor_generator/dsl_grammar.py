"""DSL 语法定义。算子清单 + 参数签名。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpDef:
    """算子定义。"""
    name: str
    params: list[tuple[str, str]]  # [(参数名, 类型)], 类型: col / int / float
    description: str = ''


# ── 算子注册表 ──────────────────────────────────

OPERATORS: dict[str, OpDef] = {}

def _reg(op: OpDef):
    OPERATORS[op.name] = op


_reg(OpDef('DELAY', [('series', 'col'), ('n', 'int')], description='前推 n 期'))
_reg(OpDef('MA', [('series', 'col'), ('n', 'int')], description='n 日简单移动平均'))
_reg(OpDef('AVG', [('series', 'col'), ('n', 'int')], description='n 日移动平均（同 MA）'))
_reg(OpDef('STDDEV', [('series', 'col'), ('n', 'int')], description='n 日滚动标准差'))
_reg(OpDef('SUM', [('series', 'col'), ('n', 'int')], description='n 日滚动求和'))
_reg(OpDef('TS_MAX', [('series', 'col'), ('n', 'int')], description='n 日滚动最大值'))
_reg(OpDef('TS_MIN', [('series', 'col'), ('n', 'int')], description='n 日滚动最小值'))
_reg(OpDef('RANK', [('series', 'col')], description='截面排名，0~1'))
_reg(OpDef('SCALE', [('series', 'col')], description='缩放到 [-1, 1]'))
_reg(OpDef('ZSCORE', [('series', 'col')], description='截面标准化'))
_reg(OpDef('CORRELATION', [('a', 'col'), ('b', 'col'), ('n', 'int')], description='滚动相关系数'))
_reg(OpDef('COVARIANCE', [('a', 'col'), ('b', 'col'), ('n', 'int')], description='滚动协方差'))
_reg(OpDef('DELTA', [('series', 'col'), ('n', 'int')], description='差分'))
_reg(OpDef('ABS', [('series', 'col')], description='绝对值'))
_reg(OpDef('SIGN', [('series', 'col')], description='符号函数'))
_reg(OpDef('LOG', [('series', 'col')], description='自然对数'))
_reg(OpDef('POWER', [('series', 'col'), ('p', 'float')], description='幂运算'))
_reg(OpDef('IF', [('cond', 'col'), ('true_v', 'col'), ('false_v', 'col')], description='条件选择'))
_reg(OpDef('EMA', [('series', 'col'), ('n', 'int')], description='指数移动平均'))
_reg(OpDef('COUNT', [('cond', 'col'), ('n', 'int')], description='n 日内条件成立次数'))
_reg(OpDef('CROSS', [('a', 'col'), ('b', 'col')], description='上穿'))
_reg(OpDef('RETURNS', [('series', 'col'), ('n', 'int')], description='n 期收益率'))
_reg(OpDef('EVERY', [('cond', 'col'), ('n', 'int')], description='n 日内条件持续成立'))
_reg(OpDef('BARSLAST', [('cond', 'col')], description='上次条件成立距今天数'))
_reg(OpDef('TS_RANK', [('series', 'col'), ('n', 'int')], description='时序排名'))
_reg(OpDef('DECAY_LINEAR', [('series', 'col'), ('n', 'int')], description='线性衰减加权平均'))
_reg(OpDef('SLOPE', [('series', 'col'), ('n', 'int')], description='线性回归斜率'))
_reg(OpDef('FORCAST', [('series', 'col'), ('n', 'int')], description='线性回归预测'))
_reg(OpDef('SQRT', [('series', 'col')], description='平方根'))
_reg(OpDef('MAX', [('a', 'col'), ('b', 'col')], description='两列取较大值'))
_reg(OpDef('MIN', [('a', 'col'), ('b', 'col')], description='两列取较小值'))
_reg(OpDef('HHV', [('series', 'col'), ('n', 'int')], description='n 日滚动最高值（同 TS_MAX）'))
_reg(OpDef('LLV', [('series', 'col'), ('n', 'int')], description='n 日滚动最低值（同 TS_MIN）'))
_reg(OpDef('TS_MEAN', [('series', 'col'), ('n', 'int')], description='n 日移动平均（同 MA）'))
_reg(OpDef('MEAN', [('series', 'col'), ('n', 'int')], description='n 日移动平均（同 MA）'))
_reg(OpDef('ADV', [('volume', 'col'), ('n', 'int')], description='n 日平均成交量'))
_reg(OpDef('SMA', [('series', 'col'), ('n', 'int'), ('m', 'int')], description='中国式移动平均'))
_reg(OpDef('WMA', [('series', 'col'), ('n', 'int')], description='加权移动平均'))
_reg(OpDef('TS_ARGMAX', [('series', 'col'), ('n', 'int')], description='窗口内最高值位置'))
_reg(OpDef('TS_ARGMIN', [('series', 'col'), ('n', 'int')], description='窗口内最低值位置'))
_reg(OpDef('HHVBARS', [('series', 'col'), ('n', 'int')], description='距窗口最高值的周期数'))
_reg(OpDef('LLVBARS', [('series', 'col'), ('n', 'int')], description='距窗口最低值的周期数'))
_reg(OpDef('AVEDEV', [('series', 'col'), ('n', 'int')], description='平均绝对偏差'))
_reg(OpDef('EXIST', [('cond', 'col'), ('n', 'int')], description='n 天内至少成立一次'))
_reg(OpDef('SUMIF', [('val', 'col'), ('cond', 'col'), ('n', 'int')], description='条件求和'))
_reg(OpDef('BARSLASTCOUNT', [('cond', 'col')], description='连续成立天数'))
_reg(OpDef('BARSSINCEN', [('cond', 'col'), ('n', 'int')], description='距 n 天内首次成立周期数'))
_reg(OpDef('LAST', [('cond', 'col'), ('a', 'int'), ('b', 'int')], description='a 天前到 b 天前一直成立'))
_reg(OpDef('VALUEWHEN', [('val', 'col'), ('cond', 'col')], description='条件成立时取值'))
_reg(OpDef('CONST', [('series', 'col')], description='末值填充全列'))
_reg(OpDef('LONGCROSS', [('a', 'col'), ('b', 'col'), ('n', 'int')], description='长期交叉'))
_reg(OpDef('PRODUCT', [('series', 'col'), ('n', 'int')], description='滚动乘积'))
_reg(OpDef('FILTER', [('cond', 'col'), ('n', 'int')], description='条件触发后 n 天置零'))
_reg(OpDef('SIGNEDPOWER', [('series', 'col'), ('n', 'float')], description='带符号幂运算'))
_reg(OpDef('DECAY_EXP', [('series', 'col'), ('alpha', 'float')], description='指数衰减加权平均'))
_reg(OpDef('TS_REGRESSION', [('y', 'col'), ('x', 'col'), ('n', 'int')], description='滚动线性回归残差'))

# ── 字段映射 ─────────────────────────────────────

# 别名修正从 field_aliases.json 加载
_ALIAS_MAP: dict[str, str] = {}

FIELD_MAP: dict[str, str] = {}


def _load_aliases(config_dir: str | None = None) -> dict[str, str]:
    """从 field_aliases.json 加载别名修正。"""
    if config_dir is None:
        config_dir = _os.path.join(_os.path.dirname(__file__), 'config')
    path = _os.path.join(config_dir, 'field_aliases.json')
    if _os.path.exists(path):
        try:
            return _json.load(open(path))
        except Exception:
            pass
    return {}


def _init_field_map(data_dict: dict | None = None,
                    aliases: dict[str, str] | None = None):
    """从数据字典构建 FIELD_MAP。

    自动生成每列 .upper() 映射，再由 aliases 修正别名。
    """
    global FIELD_MAP
    fm = {}
    if data_dict:
        for t in data_dict.get('tables', []):
            for f in t.get('fields', []):
                fm[f['name'].upper()] = f['name']
    # 别名修正覆盖
    if aliases is None:
        aliases = _ALIAS_MAP
    for alias, real in aliases.items():
        fm[alias] = real
    FIELD_MAP = fm


# 模块加载时从默认配置初始化
import json as _json, os as _os
_ALIAS_MAP = _load_aliases()
_DD_PATH = _os.path.join(_os.path.dirname(__file__), 'config', 'data_dictionary.json')
if _os.path.exists(_DD_PATH):
    try:
        _init_field_map(_json.load(open(_DD_PATH)))
    except Exception:
        _init_field_map()
else:
    _init_field_map()


# ── 辅助函数 ─────────────────────────────────────

def is_operator(name: str) -> bool:
    return name in OPERATORS


def is_field(name: str) -> bool:
    return name in FIELD_MAP


def resolve_field(name: str) -> str:
    return FIELD_MAP.get(name, name.lower())


def sync_field_map(data_dict: dict):
    """运行时重新同步 FIELD_MAP（如数据字典刷新后调用）。"""
    _init_field_map(data_dict)
