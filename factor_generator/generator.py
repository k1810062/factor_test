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
    description: str            # 字段的自然语言描述（如"行业指数收盘价"）
    table_desc: str = ''        # 表描述（如"行业指数日线行情"）
    status: str = 'missing'      # available / missing / need_derive
    alias_table: str | None = None
    alias_field: str | None = None
    matched_table: str | None = None
    matched_field: str | None = None
    confidence: float | None = None


@dataclass
class FactorInfo:
    """单因子信息。"""
    name: str
    label: str
    category: str
    domain: str
    code: str
    logic_summary: str
    data_requirements: list[RequirementInfo] = field(default_factory=list)


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

    # 2. 构建带数据字典的 system prompt
    data_dict_lines = ['# 可用数据表\n']
    for t in data_dict.get('tables', []):
        tname = t['name']
        tdesc = t.get('description', '')
        data_dict_lines.append(f'\n## {tname}（{tdesc}）')
        for f in t.get('fields', []):
            data_dict_lines.append(f'  {tname}.{f["name"]} — {f.get("description", "")}')
    data_dict_str = '\n'.join(data_dict_lines)

    system_prompt = prompt_template.replace(
        '{data_dict}', data_dict_str).replace(
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

    for fi in factor_output:
        if fi.data_requirements:
            new_reqs: list[RequirementInfo] = []
            for req in fi.data_requirements:
                new_reqs.append(req)

            fi.data_requirements = new_reqs

    return FactorOutput(factors=factor_output, raw_llm_output=raw, usage=llm_usage)


def reapply(llm_output_path: str, config_dir: str | None = None) -> FactorOutput:
    """复用已保存的 LLM 输出，重新匹配 + 替换，不调 LLM。

    用户补完数据后调用此函数，无需重新生成。
    """
    if config_dir is None:
        config_dir = _DEFAULT_CONFIG_DIR

    with open(llm_output_path, encoding='utf-8') as f:
        raw = json.load(f)

    try:
        factor_output = _parse_llm_output(raw, data_dict)
    except (KeyError, TypeError, ValueError) as e:
        return FactorOutput(factors=[], raw_llm_output=raw, error=f'解析失败: {e}')

    try:
        data_dict = _load_json(
            _resolve_config_path(config_dir, 'data_dictionary.json'))
    except FileNotFoundError as e:
        return FactorOutput(factors=factor_output, raw_llm_output=raw, error=f'数据字典不存在: {e}')

    # LLM 直接输出真实表名和字段名，不再需要匹配
    for fi in factor_output:
        for req in fi.data_requirements:
            req.status = 'available' if req.matched_table else 'missing'

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
        aliases_raw = f.get('aliases', {})
        reqs_raw = f.get('data_requirements', [])
        reqs: list[RequirementInfo] = []

        for r in reqs_raw:
            # 新格式：LLM 直接输出 table + field（真实名）
            table = r.get('table') or r.get('table_desc', '')
            field = r.get('field') or r.get('field_desc', '') or r.get('description', '')
            alias_table = r.get('alias_table') or table
            alias_field = r.get('alias_field') or field

            if not alias_table:
                for key, val in aliases_raw.items():
                    if val.get('type') == 'table' and val.get('description') == table:
                        alias_table = key
                        break

            # 校验字段是否真实存在
            _field_ok = False
            if table and field and valid_fields:
                _tbl_fields = valid_fields.get(table)
                if _tbl_fields and field in _tbl_fields:
                    _field_ok = True
            reqs.append(RequirementInfo(
                description=field,
                table_desc=table,
                status='available' if _field_ok else 'missing',
                alias_table=alias_table,
                alias_field=alias_field,
                matched_table=table if table and '.' not in table else None,
                matched_field=field,
            ))

        # 兼容旧格式：从 aliases 生成（field 级别）
        if not reqs and aliases_raw:
            for key, val in aliases_raw.items():
                if val.get('type') == 'field':
                    parts = key.split('.', 1)
                    alias_t = parts[0] if len(parts) > 1 else None
                    alias_f = parts[1] if len(parts) > 1 else parts[0]
                    table_desc = aliases_raw.get(alias_t, {}).get('description', '') if alias_t else ''
                    reqs.append(RequirementInfo(
                        description=val.get('description', ''),
                        table_desc=table_desc,
                        status='missing',
                        alias_table=alias_t,
                        alias_field=alias_f,
                    ))

        result.append(FactorInfo(
            name=f['name'],
            label=f.get('label', ''),
            category=f.get('category', ''),
            domain=f.get('domain', ''),
            code=f.get('code', ''),
            logic_summary=f.get('logic_summary', ''),
            data_requirements=reqs,
        ))

    return result
