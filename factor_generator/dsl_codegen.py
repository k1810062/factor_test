"""DSL → pandas 表达式代码生成器。"""

from .dsl_parser import DSLScript, Call, Field, BinOp, CmpOp, UnaryOp, Num
from .dsl_grammar import OPERATORS, resolve_field


def validate_fields(fields: set[str], data_dict: dict, domain: str) -> list:
    """校验 DSL 字段在数据字典中是否存在，返回 RequirementInfo 列表。"""
    from .generator import RequirementInfo

    tbl = 'stock_daily' if domain.startswith('stock') else 'industry_daily'

    valid_cols = set()
    for t in data_dict.get('tables', []):
        if t['name'] == tbl:
            valid_cols = {f['name'] for f in t.get('fields', [])}
            break

    result = []
    for dsl_name in sorted(fields):
        real_name = resolve_field(dsl_name)
        ok = real_name in valid_cols
        result.append(RequirementInfo(
            table=tbl,
            field=real_name,
            status='available' if ok else 'missing',
        ))
    return result


def _pandas_op(name: str, args: list[str], gk: str, dk: str) -> str:
    """算子名 + 参数 → pandas 表达式字符串。"""
    def _ts(expr: str, body: str) -> str:
        return f"({expr}).groupby(df['{gk}']).transform(lambda x: {body})"

    def _cs(expr: str, body: str) -> str:
        return f"({expr}).groupby(df['{dk}']).transform(lambda x: {body})"

    # 元素级运算
    if name == 'ABS': return f"np.abs({args[0]})"
    if name == 'LOG': return f"np.log({args[0]})"
    if name == 'SQRT': return f"np.sqrt({args[0]})"
    if name == 'SIGN': return f"np.sign({args[0]})"
    if name == 'POWER': return f"np.power({args[0]}, {args[1]})"
    if name == 'SIGNEDPOWER': return f"np.sign({args[0]}) * np.abs({args[0]}) ** {args[1]}"
    if name == 'MAX': return f"np.maximum({args[0]}, {args[1]})"
    if name == 'MIN': return f"np.minimum({args[0]}, {args[1]})"
    if name == 'IF': return f"np.where({args[0]}, {args[1]}, {args[2]})"

    # 时序算子（按股票分组）
    if name == 'DELAY': return _ts(args[0], f"x.shift({args[1]})")
    if name == 'DELTA': return _ts(args[0], f"x.diff({args[1]})")
    if name in ('MA', 'AVG', 'ADV', 'TS_MEAN', 'MEAN'):
        return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).mean()")
    if name == 'STDDEV': return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).std(ddof=0)")
    if name == 'SUM': return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).sum()")
    if name in ('TS_MAX', 'HHV'): return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).max()")
    if name in ('TS_MIN', 'LLV'): return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).min()")
    if name == 'RETURNS': return _ts(args[0], f"x.pct_change({args[1]})")
    if name == 'CORRELATION': return _ts(args[0], f"x.rolling({args[2]}).corr({args[1]})")
    if name == 'COVARIANCE': return _ts(args[0], f"x.rolling({args[2]}).cov({args[1]})")
    if name == 'COUNT': return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).sum()")
    if name == 'EVERY': return _ts(args[0], f"(x.rolling({args[1]}, min_periods={args[1]}).sum() == {args[1]})")
    if name == 'CROSS': return f"({args[0]} > {args[1]}) & " + _ts(args[0], f"x.shift(1) <= {args[1]}")

    # 截面算子（按日期分组）
    if name == 'RANK': return _cs(args[0], "x.rank(pct=True)")
    if name == 'ZSCORE': return _cs(args[0], "(x - x.mean()) / x.std(ddof=0)")
    if name == 'SCALE': return _cs(args[0], "2 * (x - x.min()) / (x.max() - x.min()) - 1")

    # pandas-only 算子
    if name == 'EMA': return _ts(args[0], f"x.ewm(span={args[1]}, adjust=False).mean()")
    if name == 'SMA': return _ts(args[0], f"x.ewm(alpha={args[1]}/{args[2]}, adjust=False).mean()")
    if name == 'WMA': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.average(y, weights=np.arange(1,{args[1]}+1)))")
    if name == 'TS_RANK': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: pd.Series(y).rank(pct=True).iloc[-1])")
    if name == 'DECAY_LINEAR': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.average(y, weights=np.linspace(1,0,len(y))))")
    if name == 'SLOPE': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.polyfit(range(len(y)),y,1)[0])")
    if name == 'FORCAST': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.polyval(np.polyfit(range(len(y)),y,1),len(y)-1))")
    if name == 'BARSLAST': return _ts(args[0], "_barslast(x)")
    if name == 'TS_ARGMAX': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.argmax(y[::-1]))")
    if name == 'TS_ARGMIN': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.argmin(y[::-1]))")
    if name == 'HHVBARS': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: int(np.argmax(y[::-1]))+1)")
    if name == 'LLVBARS': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: int(np.argmin(y[::-1]))+1)")
    if name == 'AVEDEV': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: np.abs(y - y.mean()).mean())")
    if name == 'EXIST': return _ts(args[0], f"x.rolling({args[1]}, min_periods=1).sum() > 0")
    if name == 'SUMIF': return f"(np.where({args[1]}, {args[0]}, 0)).groupby(df['{gk}']).transform(lambda x: x.rolling({args[2]}, min_periods=1).sum())"
    if name == 'BARSLASTCOUNT': return _ts(args[0], "_barslastcount(x)")
    if name == 'BARSSINCEN': return _ts(args[0], f"x.rolling({args[1]}).apply(lambda y: len(y)-1-np.argmax(y) if np.any(y) else {args[1]})")
    if name == 'LAST': return _ts(args[0], f"x.rolling({args[1]}+1).apply(lambda y: float(np.all(y[::-1][{args[2]}:{args[1]}])))")
    if name == 'VALUEWHEN': return f"({args[0]}).where({args[1]}, None).groupby(df['{gk}']).transform(lambda x: x.ffill())"
    if name == 'CONST': return f"({args[0]}).transform(lambda x: pd.Series(x.iloc[-1], index=x.index))"
    if name == 'LONGCROSS': return _ts(args[0], f"x.rolling({args[2]}+1).apply(lambda y: float(np.all(y[::-1][1:{args[2]}+1] < {args[1]}) and y.iloc[-1] > {args[1]}))")
    if name == 'PRODUCT': return _ts(args[0], f"x.rolling({args[1]}).apply(np.prod)")
    if name == 'FILTER': return _ts(args[0], f"_filter(x, {args[1]})")

    raise ValueError(f'no pandas implementation for {name}')


def _gen_pandas_expr(expr, gk='stock_code', dk='trade_date') -> str:
    """DSL AST → pandas 表达式字符串。"""
    if isinstance(expr, Num):
        v = expr.val
        return str(int(v)) if isinstance(v, float) and v == int(v) else str(v)
    if isinstance(expr, Field):
        return f"df['{resolve_field(expr.name)}']"
    if isinstance(expr, UnaryOp):
        sub = _gen_pandas_expr(expr.expr, gk, dk)
        return f'(-{sub})'
    if isinstance(expr, (BinOp, CmpOp)):
        left = _gen_pandas_expr(expr.left, gk, dk)
        right = _gen_pandas_expr(expr.right, gk, dk)
        return f'({left} {expr.op} {right})'
    if isinstance(expr, Call):
        op = OPERATORS.get(expr.name)
        if not op:
            raise ValueError(f'unknown operator: {expr.name}')
        args = [_gen_pandas_expr(a, gk, dk) for a in expr.args]
        return _pandas_op(expr.name, args, gk, dk)
    raise TypeError(f'unknown node: {type(expr).__name__}')


def gen_pandas(script, factor_name, domain, label='') -> str:
    _label = label or factor_name
    is_stock = domain.startswith('stock')
    tbl = 'stock_daily' if is_stock else 'industry_daily'
    gk = 'stock_code' if is_stock else 'industry_code'
    kc = [gk, 'trade_date']
    dk = 'trade_date'

    field_sql = ', '.join(resolve_field(f) for f in sorted(script.fields))
    key_sql = ', '.join(kc)

    expr_code = _gen_pandas_expr(script.expr, gk=gk, dk=dk)

    # BARSLAST / BARSLASTCOUNT 需要辅助函数
    helper = ''
    if 'BARSLAST' in script.operators or 'BARSLASTCOUNT' in script.operators or 'FILTER' in script.operators:
        helper = '''
def _barslast(s):
    res = [0] * len(s)
    cnt = 0
    for i in reversed(range(len(s))):
        if s.iloc[i]: cnt = 0
        else: cnt += 1
        res[i] = cnt
    return res

def _barslastcount(s):
    rt = [0] * len(s)
    cnt = 0
    for i in range(len(s)):
        cnt = cnt + 1 if s.iloc[i] else 0
        rt[i] = cnt
    return rt

def _filter(s, n):
    res = [0] * len(s)
    cd = 0
    for i in range(len(s)):
        if cd > 0:
            cd -= 1
        elif s.iloc[i]:
            res[i] = 1
            cd = n
    return res
'''

    return (
        f"@factor(name='{factor_name}', category='pv', label='{_label}', domain='{domain}')\n"
        f"def {factor_name}(api):\n"
        f"    import pandas as pd, numpy as np\n"
        f"    df = api.query('''SELECT {key_sql}, {field_sql} FROM {tbl}''')\n"
        f"    df = df.sort_values({kc}).reset_index(drop=True)\n"
        f"    df['{factor_name}'] = {expr_code}\n"
        f"    return df[['{gk}', 'trade_date', '{factor_name}']]\n"
        f"{helper}"
    )


def compile_dsl(dsl: str, name: str, domain: str = 'stock', label: str = '',
                data_dict=None) -> tuple[str, list]:
    """编译 DSL 公式 → (@factor 代码, 字段校验列表)。
    DSL 统一走 pandas 路径，SQL 只取原始数据。"""
    from .dsl_parser import parse_dsl
    script = parse_dsl(dsl)

    # 字段校验（不阻断编译）
    fields_info = validate_fields(script.fields, data_dict, domain) if data_dict else []

    code = gen_pandas(script, name, domain, label)
    return code, fields_info
