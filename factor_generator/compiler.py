"""Compiler：SQL formula → @factor 代码。

用法：
    from factor_generator.compiler import compile_factor, compile_pending
    code = compile_factor(fi)        # FactorInfo → str
"""

import sqlparse
import duckdb
from factor_generator.generator import FactorInfo


def _validate_sql(sql: str) -> str | None:
    """用 DuckDB EXPLAIN 校验 SQL 语法，成功返回 None，失败返回错误信息。"""
    con = duckdb.connect()
    try:
        con.execute(f'EXPLAIN {sql}')
        return None
    except Exception as e:
        return str(e)[:200]
    finally:
        con.close()


def fmt_sql(raw: str) -> str:
    """格式化 SQL 为人类可读。"""
    return sqlparse.format(raw, reindent=True, keyword_case='upper',
                           indent_width=4, strip_comments=True)


def compile_factor(fi: FactorInfo) -> str:
    """FactorInfo → @factor 装饰器 + 函数代码。"""
    # DSL：总是重新编译，代码可能已更新
    if fi.dsl:
        from .dsl_codegen import compile_dsl
        code, _ = compile_dsl(fi.dsl, fi.name, fi.domain)
        fi.code = code
        return fi.code

    # raw 模式：直接使用已有代码
    if fi.raw:
        if fi.code:
            return fi.code
        raise ValueError(f'[{fi.name}] raw 模式但 code 为空')
        from .dsl_codegen import compile_dsl
        fi.code = compile_dsl(fi.dsl, fi.name, fi.domain)
        return fi.code

    # formula 模式
    sql = fi.formula.strip()
    if not sql:
        raise ValueError(f'[{fi.name}] formula 为空，且非 raw 模式')
    if not sql.upper().lstrip().startswith(('SELECT', 'WITH')):
        raise ValueError(f'[{fi.name}] formula 必须是完整 SQL 查询（以 SELECT/WITH 开头）')

    err = _validate_sql(sql)
    if err:
        raise ValueError(f'[{fi.name}] SQL 预检查失败: {err}')

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
