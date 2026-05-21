"""因子生成器主入口。

编排流程：加载配置 → 调用 LLM → 匹配数据字典 → 返回结构化结果。
"""

import json
import os
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any

import yaml

from factor_generator.llm_client import LLMClient, LLMError
from factor_generator.matcher import FieldMatcher

# 默认配置目录（相对于本文件）
_DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')


@dataclass
class RequirementInfo:
    """数据需求标注结果。"""
    description: str            # 自然语言描述（来自 LLM）
    status: str                 # available / missing / need_derive
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


def _load_json(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _load_text(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def _load_yaml(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _resolve_config_path(config_dir: str, filename: str) -> str:
    path = os.path.join(config_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f'配置文件不存在: {path}')
    return path


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
        data_dict = _load_yaml(
            _resolve_config_path(config_dir, 'data_dictionary.yaml'))
    except FileNotFoundError as e:
        return FactorOutput(factors=[], error=str(e))
    except (json.JSONDecodeError, yaml.YAMLError) as e:
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

    # 4. 匹配数据字典（失败不影响因子代码回传）
    matcher = FieldMatcher(data_dict)
    match_ok = matcher.build_index()

    for fi in factor_output:
        if fi.data_requirements:
            req_dicts = [{'description': r.description}
                         for r in fi.data_requirements]
            if match_ok:
                matched = matcher.match(req_dicts)
            else:
                matched = [
                    {'description': r.description, 'status': 'missing',
                     'matched_table': None, 'matched_field': None,
                     'confidence': None}
                    for r in fi.data_requirements
                ]
            fi.data_requirements = [
                RequirementInfo(
                    description=m.get('description', ''),
                    status=m['status'],
                    matched_table=m.get('matched_table'),
                    matched_field=m.get('matched_field'),
                    confidence=m.get('confidence'),
                )
                for m in matched
            ]

    return FactorOutput(factors=factor_output, raw_llm_output=raw)


def _parse_llm_output(raw: dict) -> list[FactorInfo]:
    """解析 LLM 返回的 JSON 为 FactorInfo 列表。"""
    factors_raw = raw.get('factors', [])
    if not factors_raw:
        raise ValueError('LLM 输出缺少 factors 字段')

    result: list[FactorInfo] = []
    for f in factors_raw:
        reqs_raw = f.get('data_requirements', [])
        reqs = [
            RequirementInfo(description=r.get('description', ''))
            for r in reqs_raw
        ]
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
