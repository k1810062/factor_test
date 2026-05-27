"""Compiler：SQL formula → @factor 代码。

用法：
    from factor_generator.compiler import compile_factor, compile_pending
    code = compile_factor(fi)        # FactorInfo → str
"""

import sqlparse
from factor_generator.generator import FactorInfo


def fmt_sql(raw: str) -> str:
    """格式化 SQL 为人类可读。"""
    return sqlparse.format(raw, reindent=True, keyword_case='upper',
                           indent_width=4, strip_comments=True)


def compile_factor(fi: FactorInfo) -> str:
    """FactorInfo → @factor 装饰器 + 函数代码。"""
    # raw 模式：直接使用已有代码
    if fi.raw:
        if not fi.code:
            raise ValueError(f'[{fi.name}] raw 模式但 code 为空')
        return fi.code

    # formula 模式
    sql = fi.formula.strip()
    if not sql:
        raise ValueError(f'[{fi.name}] formula 为空，且非 raw 模式')
    if not sql.upper().lstrip().startswith(('SELECT', 'WITH')):
        raise ValueError(f'[{fi.name}] formula 必须是完整 SQL 查询（以 SELECT/WITH 开头）')

    formatted = fmt_sql(sql)
    return (
        f"@factor(name='{fi.name}', category='{fi.category}', "
        f"label='{fi.label}', domain='{fi.domain}')\n"
        f"def {fi.name}(api):\n"
        f"    return api.query('''\n"
        f"{formatted}\n"
        f"''')\n"
    )


def compile_pending(items: list[dict]) -> list[dict]:
    """给 pending 列表每项编译 code 字段。原地修改并返回。"""
    from factor_generator.generator import FactorInfo
    for item in items:
        fi = item['data']
        if isinstance(fi, FactorInfo):
            item['data'].code = compile_factor(fi)
    return items
