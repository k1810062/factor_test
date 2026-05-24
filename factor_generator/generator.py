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
from factor_generator.matcher import FieldMatcher

_DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')


@dataclass
class RequirementInfo:
    """数据需求标注结果。"""
    description: str
    status: str                  # available / missing / need_derive
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

    # 2. 调用 LLM
    try:
        client = LLMClient(api_config)
        system_prompt = prompt_template.replace(
            '{report_text}', report_text)
        raw = client.call_json(system_prompt, '')
    except (LLMError, json.JSONDecodeError, KeyError) as e:
        tb = traceback.format_exc()
        return FactorOutput(
            factors=[],
            error=f'LLM 调用失败: {e}\n{tb}',
        )

    # 3. 解析 LLM 输出
    try:
        factor_output = _parse_llm_output(raw)
    except (KeyError, TypeError, ValueError) as e:
        return FactorOutput(
            factors=[],
            raw_llm_output=raw,
            error=f'LLM 输出解析失败: {e}',
        )

    # 4. 匹配数据字典
    matcher = FieldMatcher(data_dict)
    match_ok = matcher.build_index()

    for fi in factor_output:
        if fi.data_requirements:
            req_dicts = [
                {'description': r.description}
                for r in fi.data_requirements
            ]
            if match_ok:
                matched = matcher.match(req_dicts)
            else:
                matched = [
                    {'description': r.description, 'status': 'missing',
                     'matched_table': None, 'matched_field': None,
                     'confidence': None}
                    for r in fi.data_requirements
                ]

            # 收集 alias → real 映射
            table_map: dict[str, str] = {}
            field_map: dict[str, str] = {}
            new_reqs: list[RequirementInfo] = []

            for req, m in zip(fi.data_requirements, matched):
                new_reqs.append(RequirementInfo(
                    description=m.get('description', ''),
                    status=m['status'],
                    alias_table=req.alias_table,
                    alias_field=req.alias_field,
                    matched_table=m.get('matched_table'),
                    matched_field=m.get('matched_field'),
                    confidence=m.get('confidence'),
                ))
                if (m['status'] == 'available'
                        and m.get('matched_table')
                        and req.alias_table):
                    table_map[req.alias_table] = m['matched_table']
                if (m['status'] == 'available'
                        and m.get('matched_field')
                        and req.alias_field):
                    field_map[req.alias_field] = m['matched_field']

            fi.data_requirements = new_reqs

            # 5. 代码别名替换
            if table_map or field_map:
                fi.code = _apply_code_mapping(
                    fi.code, table_map, field_map)

    return FactorOutput(factors=factor_output, raw_llm_output=raw)


def _parse_llm_output(raw: dict) -> list[FactorInfo]:
    """解析 LLM 返回的 JSON 为 FactorInfo 列表。"""
    factors_raw = raw.get('factors', [])
    if not factors_raw:
        raise ValueError('LLM 输出缺少 factors 字段')

    result: list[FactorInfo] = []
    for f in factors_raw:
        # 解析 aliases 映射
        aliases_raw = f.get('aliases', {})

        # 从 aliases 和 data_requirements 合并生成需求列表
        reqs_raw = f.get('data_requirements', [])
        reqs: list[RequirementInfo] = []

        for r in reqs_raw:
            desc = r.get('description', '')
            alias_table = r.get('alias_table') or r.get('table')
            alias_field = r.get('alias_field') or r.get('field')

            # 如果没有单独指定 alias，尝试从 aliases 反查
            if not alias_table:
                for key, val in aliases_raw.items():
                    if val.get('type') == 'table' and val.get('description') == desc:
                        alias_table = key
                        break

            reqs.append(RequirementInfo(
                description=desc,
                status='missing',
                alias_table=alias_table,
                alias_field=alias_field,
            ))

        # 如果 LLM 没有输出 data_requirements，
        # 从 aliases 自动生成（field 级别）
        if not reqs and aliases_raw:
            for key, val in aliases_raw.items():
                if val.get('type') == 'field':
                    parts = key.split('.', 1)
                    alias_t = parts[0] if len(parts) > 1 else None
                    alias_f = parts[1] if len(parts) > 1 else parts[0]
                    reqs.append(RequirementInfo(
                        description=val.get('description', ''),
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
