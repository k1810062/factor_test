"""因子生成器主入口。

编排流程：加载配置 → 调用 LLM → 匹配数据字典 → 代码别名替换 → 返回结构化结果。
"""

import json
import os
import re
import traceback
from dataclasses import dataclass, field
from typing import Any

from factor_generator.llm_client import LLMClient, LLMError
# LLM 直接输出真实表名和字段名，不再需要 embedding 匹配

_DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')


@dataclass
class RequirementInfo:
    """数据需求标注结果。"""
    table: str = ''              # 表名
    field: str = ''              # 字段名
    status: str = 'missing'      # available / missing


@dataclass
class FactorInfo:
    """单因子信息。"""
    name: str
    label: str
    category: str
    domain: str
    formula: str = ''                               # SQL 查询
    dsl: str = ''                                   # DSL 公式表达式
    code: str = ''                                  # @factor 代码（compiler 填充或 raw 模式直接用）
    raw: bool = False                               # 是否 raw 模式（完整代码，不走 compiler）
    logic_summary: str = ''
    tables_needed: list[str] = field(default_factory=list)
    fields_needed: list[RequirementInfo] = field(default_factory=list)


@dataclass
class FactorOutput:
    """生成结果。"""
    factors: list[FactorInfo]
    raw_llm_output: dict | None = None
    usage: dict | None = None
    error: str | None = None


# ── 工具函数 ──────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _load_text(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def _resolve_config_path(config_dir: str, filename: str) -> str:
    path = os.path.join(config_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f'配置文件不存在: {path}')
    return path


def generate_toc(
    report_text: str,
    config_dir: str | None = None,
) -> FactorOutput:
    """提取因子目录（TOC），不含完整代码。"""
    if config_dir is None:
        config_dir = _DEFAULT_CONFIG_DIR

    try:
        api_config = _load_json(
            _resolve_config_path(config_dir, 'api_config.json'))
        prompt_template = _load_text(
            os.path.join(config_dir, 'prompt_toc.txt'))
    except FileNotFoundError as e:
        return FactorOutput(factors=[], error=str(e))
    except json.JSONDecodeError as e:
        return FactorOutput(factors=[], error=f'配置文件格式错误: {e}')

    system_prompt = prompt_template.replace(
        '{report_text}', report_text)

    try:
        client = LLMClient(api_config)
        raw, llm_usage = client.call_json(system_prompt, '')
    except (LLMError, json.JSONDecodeError, KeyError) as e:
        import traceback
        return FactorOutput(factors=[], error=f'LLM 调用失败: {e}\n{traceback.format_exc()}')

    result = FactorOutput(factors=[], raw_llm_output=raw, usage=llm_usage)
    factors_raw = raw.get('factors', [])
    for f in factors_raw:
        result.factors.append(FactorInfo(
            name=f.get('name', ''),
            label=f.get('label', ''),
            category=f.get('category', ''),
            domain=f.get('domain', ''),
            formula='',
            logic_summary=f.get('logic_summary', ''),
        ))
    return result


def _apply_code_mapping(code: str,
                         table_map: dict[str, str],
                         field_map: dict[str, str]) -> str:
    """将代码中的别名替换为真实表名和字段名。

    Args:
        code: 原始代码（含别名）
        table_map: {alias_table: real_table}
        field_map: {alias_field: real_field}

    Returns:
        替换后的代码
    """
    result = code

    # 替换表名：api.table('alias' → api.table('real'，支持带后续参数
    for alias, real in table_map.items():
        result = re.sub(
            rf"(api\.table\('){alias}(')",
            rf'\g<1>{real}\g<2>',
            result,
        )
        result = re.sub(
            rf"(FROM\s+){alias}(\s)",
            rf'\g<1>{real}\g<2>',
            result,
            flags=re.IGNORECASE,
        )
        result = re.sub(
            rf"(JOIN\s+){alias}(\s)",
            rf'\g<1>{real}\g<2>',
            result,
            flags=re.IGNORECASE,
        )

    # 替换字段名：用英文单词边界 \b 避免误替换子串
    for alias, real in sorted(field_map.items(), key=lambda x: -len(x[0])):
        # 在 SQL 中、df['alias']、.assign(alias= 等上下文替换
        result = re.sub(
            rf'\b{re.escape(alias)}\b',
            real,
            result,
        )

    return result


# ── 主逻辑 ──────────────────────────────────


def generate(
    report_text: str,
    config_dir: str | None = None,
) -> FactorOutput:
    """主入口：读研报 → 生成因子代码 + 数据需求清单。

    Args:
        report_text: 研报或因子想法文本
        config_dir: 配置目录路径，默认使用 factor_generator/config/

    Returns:
        FactorOutput 包含因子列表和数据需求标注
    """
    if config_dir is None:
        config_dir = _DEFAULT_CONFIG_DIR

    # 1. 加载配置
    try:
        api_config = _load_json(
            _resolve_config_path(config_dir, 'api_config.json'))
        prompt_template = _load_text(
            _resolve_config_path(config_dir, 'prompt_template.txt'))
        data_dict = _load_json(
            _resolve_config_path(config_dir, 'data_dictionary.json'))
    except FileNotFoundError as e:
        return FactorOutput(factors=[], error=str(e))
    except json.JSONDecodeError as e:
        return FactorOutput(factors=[], error=f'配置文件格式错误: {e}')

    # 2. 构建 system prompt（不再注入数据字典）
    system_prompt = prompt_template.replace(
        '{report_text}', report_text)

    try:
        client = LLMClient(api_config)
        raw, llm_usage = client.call_json(system_prompt, '')
    except (LLMError, json.JSONDecodeError, KeyError) as e:
        tb = traceback.format_exc()
        return FactorOutput(
            factors=[],
            error=f'LLM 调用失败: {e}\n{tb}',
        )

    # 3. 解析 LLM 输出
    try:
        factor_output = _parse_llm_output(raw, data_dict)
    except (KeyError, TypeError, ValueError) as e:
        return FactorOutput(
            factors=[],
            raw_llm_output=raw,
            error=f'LLM 输出解析失败: {e}',
        )

    return FactorOutput(factors=factor_output, raw_llm_output=raw, usage=llm_usage)


def reapply(llm_output_path: str, config_dir: str | None = None) -> FactorOutput:
    """复用已保存的 LLM 输出，重新匹配，不调 LLM。
    用户补完数据后调用此函数，无需重新生成。
    """
    if config_dir is None:
        config_dir = _DEFAULT_CONFIG_DIR

    try:
        data_dict = _load_json(
            _resolve_config_path(config_dir, 'data_dictionary.json'))
    except FileNotFoundError as e:
        return FactorOutput(factors=[], error=f'数据字典不存在: {e}')

    with open(llm_output_path, encoding='utf-8') as f:
        raw = json.load(f)

    try:
        factor_output = _parse_llm_output(raw, data_dict)
    except (KeyError, TypeError, ValueError) as e:
        return FactorOutput(factors=[], raw_llm_output=raw, error=f'解析失败: {e}')

    # 重新校验 available/missing（数据字典可能已更新）
    valid_fields: dict[str, set[str]] = {}
    for t in data_dict.get('tables', []):
        valid_fields[t['name']] = {f['name'] for f in t.get('fields', [])}
    for fi in factor_output:
        for req in fi.fields_needed:
            if valid_fields.get(req.table) and req.field in valid_fields[req.table]:
                req.status = 'available'

    return FactorOutput(factors=factor_output, raw_llm_output=raw)


def _parse_llm_output(raw: dict, data_dict=None) -> list[FactorInfo]:
    """解析 LLM 返回的 JSON 为 FactorInfo 列表。"""
    # 构建可查字段集合
    valid_fields: dict[str, set[str]] = {}
    if data_dict:
        for t in data_dict.get('tables', []):
            valid_fields[t['name']] = {f['name'] for f in t.get('fields', [])}

    factors_raw = raw.get('factors', [])
    if not factors_raw:
        raise ValueError('LLM 输出缺少 factors 字段')

    result: list[FactorInfo] = []
    for f in factors_raw:
        # 解析字段需求（格式：表名.字段名）
        fields_raw = f.get('fields_needed', [])
        reqs: list[RequirementInfo] = []
        for entry in fields_raw:
            entry_str = str(entry)
            if '.' in entry_str:
                tbl, col = entry_str.split('.', 1)
            else:
                tbl, col = '', entry_str
            _ok = bool(tbl and col and valid_fields and
                       valid_fields.get(tbl) and col in valid_fields[tbl])
            reqs.append(RequirementInfo(
                table=tbl, field=col,
                status='available' if _ok else 'missing',
            ))

        # tables_needed（简单字符串列表）
        tables_raw = f.get('tables_needed', [])

        # DSL 模式：编译公式 → @factor 代码 + 字段校验
        dsl_expr = f.get('dsl', '')
        raw_mode = f.get('raw', False) or bool(dsl_expr)
        if dsl_expr:
            from .dsl_codegen import compile_dsl
            code_val, fields_info = compile_dsl(
                dsl_expr, f.get('name', ''), f.get('domain', 'stock'),
                label=f.get('label', ''), data_dict=data_dict)
            reqs = fields_info  # 编译器的字段校验覆盖 LLM 输出
        else:
            code_val = f.get('code', '') if raw_mode else ''

        result.append(FactorInfo(
            name=f['name'],
            label=f.get('label', ''),
            category=f.get('category', ''),
            domain=f.get('domain', ''),
            formula=f.get('formula', ''),
            dsl=f.get('dsl', ''),
            code=code_val,
            raw=raw_mode or bool(f.get('dsl', '')),
            logic_summary=f.get('logic_summary', ''),
            tables_needed=list(tables_raw),
            fields_needed=reqs,
        ))

    return result
