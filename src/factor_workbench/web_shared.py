"""共享模块：工具函数、数据加载、AI/TOC 持久化。

不包含任何 st.xxx widget 调用。两个 page 文件 import * 后使用。
"""

import ast, time, re
import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob, shutil, numpy as np, sqlparse
from code_editor import code_editor

from factor_workbench.analysis.chart_renderer import (
    load_ic_data, load_ret_data,
    render_ic_cumulative, render_long_short,
    render_decile_bar, render_win_rate, render_ic_distribution,
    render_metrics_table,
)
from factor_workbench.engine.registry import get_factors, load_factor_modules, _FACTORS
from pathlib import Path
from factor_workbench.analysis.auto_config import generate_config

BASE = str(Path(__file__).resolve().parent.parent.parent)  # llm_factors/
generate_config()
load_factor_modules(['factors'])

csv_path = os.path.join(BASE, 'output/result/factor_summary.csv')
_csv_files = sorted(glob.glob(os.path.join(BASE, 'output/result/*_factor_summary.csv')))
TEMPLATE = ''


def _find_func(txt, name):
    """在文件中查找 @factor 函数，返回 (start, end) 或 None。"""
    decor = f"@factor(name='{name}'"
    i = txt.find(decor)
    if i >= 0:
        nxt = txt.find('\n@factor(', i + 1)
        if nxt < 0:
            nxt = txt.find('\nfrom ', i + 1)
        if nxt < 0:
            nxt = len(txt)
        return i, nxt
    return None


def _parse_decorators(code):
    """从代码中提取 (name, kind, domain) 列表。"""
    tree = ast.parse(code)
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            dec = node.decorator_list[0]
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                name = next((ast.literal_eval(kw.value) for kw in dec.keywords if kw.arg == 'name'), None)
                domain = next((ast.literal_eval(kw.value) for kw in dec.keywords if kw.arg == 'domain'), 'stock')
                if name and dec.func.id == 'factor':
                    items.append((name, 'factor', domain))
    return items


def _get_func_code(name, kind, domain=None):
    """从对应类型目录提取函数代码。domain 指定时只搜对应文件。"""
    base = 'factors'
    for f in sorted(glob.glob(f'{BASE}/{base}/*.py')):
        if not os.path.exists(f):
            continue
        if domain and domain not in os.path.basename(f):
            continue
        r = _find_func(open(f).read(), name)
        if r:
            i, e = r
            return open(f).read()[i:e].strip()
    return None


def _extract_func(code, name, kind='factor'):
    """从多函数代码块中提取指定名称的函数。"""
    i = code.find(f"@{kind}(name='{name}'")
    if i < 0:
        return None
    nxt = len(code)
    for k in ('factor', 'metric'):
        p = code.find(f'\n@{k}(', i + 1)
        if 0 < p < nxt:
            nxt = p
    return code[i:nxt].strip()


def _replace_factor(name, kind, code, domain=None):
    """替换文件中的同名函数。优先搜索对应类型目录。domain 指定时追加到对应文件。"""
    func_code = _extract_func(code, name, kind)
    if not func_code:
        return
    base = os.path.join(BASE, 'features') if kind == 'feature' else os.path.join(BASE, 'factors')
    other = os.path.join(BASE, 'features') if kind != 'feature' else os.path.join(BASE, 'factors')
    search = sorted(glob.glob(f'{base}/*.py')) + sorted(glob.glob(f'{other}/*.py'))
    for f in search:
        if not os.path.exists(f):
            continue
        txt = open(f).read()
        r = _find_func(txt, name)
        if not r:
            continue
        i, e = r
        open(f, 'w').write(txt[:i] + func_code + '\n' + txt[e:])
        print(f'  [{name}] 已替换')
        return True
    print(f'  [{name}] 未找到，追加到末尾')
    base_dir = 'features' if kind == 'feature' else 'factors'
    domain = domain or 'stock'
    target = os.path.join(BASE, f'{base_dir}/{domain}_{base_dir}.py')
    with open(target, 'a') as f:
        f.write('\n\n' + func_code + '\n')
    return True


def _run_scratch(code, force=False):
    """写临时文件 → 跑 scratch.py → 返回 (stdout, stderr)。"""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    tmp.write(code)
    tmp_path = tmp.name
    tmp.close()
    env = os.environ.copy()
    src_dir = os.path.join(BASE, 'src')
    env['PYTHONPATH'] = f'{src_dir}:{env.get("PYTHONPATH", "")}'
    cmd = [sys.executable, '-m', 'factor_workbench.scratch']
    if force:
        cmd.append('--force')
    cmd.append(tmp_path)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, env=env)
    os.unlink(tmp_path)
    return result.stdout, result.stderr


def _delete_factor(name, domain=None):
    """从 .py 文件、因子库、分析结果中彻底删除一个因子。"""
    from factor_workbench.engine.registry import get_factor as _gf
    meta = _gf(name, domain) if domain else get_factors().get(name)
    if not meta:
        return
    domain, cat = meta.domain, meta.category

    # 1. 从 .py 文件移除函数
    for f in sorted(glob.glob(f'{BASE}/factors/*.py')):
        txt = open(f).read()
        r = _find_func(txt, name)
        if r:
            i, e = r
            open(f, 'w').write(txt[:i] + txt[e:])
            print(f'  [删除] 已从 {os.path.basename(f)} 移除函数')

    # 2. 从因子库 parquet 删除列
    from config.domain_config import DOMAIN_CONFIG
    if domain in DOMAIN_CONFIG:
        fp = f'{BASE}/output/factor_library/{domain}_factors.parquet'
        if os.path.exists(fp):
            _lib = pd.read_parquet(fp)
            if name in _lib.columns:
                _lib = _lib.drop(columns=[name])
                _lib.to_parquet(fp, index=False)
                print(f'  [删除] 已从 {fp} 移除数据列')

    # 3. 删分析结果
    _ad = f'{BASE}/output/analysis/{domain}'
    for _d in sorted(glob.glob(f'{_ad}*/{cat}/{name}')):
        shutil.rmtree(_d)
        print(f'  [删除] 已删除分析目录 {_d}')

    # 4. 从汇总 CSV 删除行
    _csv = f'{BASE}/output/result/{domain}_factor_summary.csv'
    if os.path.exists(_csv):
        _fdf = pd.read_csv(_csv)
        _fdf = _fdf[_fdf['factor'] != name]
        _fdf.to_csv(_csv, index=False, encoding='utf-8-sig')
        print(f'  [删除] 已从 {domain}_factor_summary.csv 移除')

    # 5. 清注册
    _FACTORS.clear()
    load_factor_modules(['factors'])
    print(f'  [删除] {name} 已彻底删除')


# ---- 因子索引 ----
import pandas as pd

df = None
full_period = pd.DataFrame()
for _csv in _csv_files:
    _d = pd.read_csv(_csv)
    _domain = os.path.basename(_csv).replace('_factor_summary.csv', '')
    _d['domain'] = _domain
    df = pd.concat([df, _d]) if df is not None else _d
if df is not None and not df.empty:
    full_period = df[df['period'] == 'full'].copy()

factor_index = {}
for _key, meta in _FACTORS.items():
    factor_index[_key] = {
        'factor': meta.name, 'label': meta.label,
        'cat': meta.category, 'domain': meta.domain,
    }
if not full_period.empty:
    for _, row in full_period.iterrows():
        fname = row['factor']
        for _v in factor_index.values():
            if _v['factor'] == fname and _v['domain'] == row.get('domain', ''):
                for col in row.index:
                    if col not in ('factor', 'label', 'cat', 'period'):
                        _v[col] = row[col]
                break

all_factors = pd.DataFrame(list(factor_index.values()))
_disp_labels = {
    'factor': '因子名', 'label': '标签', 'cat': '分类', 'domain': '领域',
    'ic_T1': 'IC均值', 'icir_T1': 'ICIR',
    'long_win': '多头胜率', 'kurtosis': '峰度',
}
disp_cols = [c for c in _disp_labels if c in all_factors.columns]


# ---- AI 因子持久化（按 domain 独立存储）----
def _ai_file(domain):
    return os.path.join(BASE, 'output', f'ai_pending_{domain}.json')


def _save_ai(domain):
    ai_pending = st.session_state.get(f'ai_pending_{domain}', [])
    data = {
        'next_id': st.session_state.get(f'ai_next_id_{domain}', 0),
        'items': [{
            'id': p['id'],
            'name': p['data'].name, 'label': p['data'].label,
            'category': p['data'].category, 'domain': p['data'].domain,
            'formula': p['data'].formula, 'dsl': p['data'].dsl, 'code': p['data'].code,
            'raw': p['data'].raw, 'logic_summary': p['data'].logic_summary,
            'tables_needed': p['data'].tables_needed,
            'fields_needed': [
                {'table': r.table, 'field': r.field, 'status': r.status}
                for r in p['data'].fields_needed
            ],
        } for p in ai_pending],
    }
    os.makedirs(os.path.dirname(_ai_file(domain)), exist_ok=True)
    json.dump(data, open(_ai_file(domain), 'w'), ensure_ascii=False, indent=2)


# ── 配置驱动的展示映射 ──────────────────────────────

MULTI_CHARTS = {'ic_distribution'}

CHART_MAP = {
    'ic_cumulative': (load_ic_data, render_ic_cumulative),
    'ic_distribution': (load_ic_data, render_ic_distribution),
    'long_short': (load_ret_data, render_long_short),
    'decile_bar': (load_ret_data, render_decile_bar),
    'win_rate': (load_ret_data, render_win_rate),
    'long_short_T1': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T1'), render_long_short),
    'decile_bar_T1': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T1'), render_decile_bar),
    'win_rate_T1': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T1'), render_win_rate),
    'long_short_T5': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T5'), render_long_short),
    'decile_bar_T5': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T5'), render_decile_bar),
    'win_rate_T5': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T5'), render_win_rate),
    'long_short_T10': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T10'), render_long_short),
    'decile_bar_T10': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T10'), render_decile_bar),
    'win_rate_T10': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T10'), render_win_rate),
    'long_short_T22': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T22'), render_long_short),
    'decile_bar_T22': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T22'), render_decile_bar),
    'win_rate_T22': (lambda b,n,c,**kw: load_ret_data(b,n,c,**kw,suffix='_T22'), render_win_rate),
}


def _build_req_summary(pending):
    """聚合所有 pending 因子的字段需求，按 table 分组。"""
    summary = {}
    for item in pending:
        fi = item['data']
        for r in fi.fields_needed:
            key = (r.table, r.field)
            if key not in summary:
                summary[key] = {'table': r.table, 'field': r.field,
                                'status': r.status, 'needed_by': []}
            summary[key]['needed_by'].append(fi.name)
            if r.status != 'available':
                summary[key]['status'] = 'missing'
    tables = {}
    for info in summary.values():
        tables.setdefault(info['table'], []).append(info)
    return tables


def _refresh_data(domain):
    """重新扫描数据，更新 pending 因子的字段可用性。"""
    subprocess.run([sys.executable, 'scripts/scan_schema.py'], cwd=BASE, capture_output=True)
    dd_path = os.path.join(BASE, 'factor_generator/config/data_dictionary.json')
    if not os.path.exists(dd_path):
        return
    data_dict = json.load(open(dd_path))
    from factor_generator.dsl_grammar import sync_field_map
    sync_field_map(data_dict)
    valid = {}
    for t in data_dict.get('tables', [],):
        valid[t['name']] = {f['name'] for f in t.get('fields', [])}
    ai_pending = st.session_state.get(f'ai_pending_{domain}', [])
    for item in ai_pending:
        for r in item['data'].fields_needed:
            r.status = 'available' if (valid.get(r.table) and r.field in valid[r.table]) else 'missing'
    _save_ai(domain)


def _load_ai(domain):
    """加载指定 domain 的待处理因子。"""
    fp = _ai_file(domain)
    ai_key = f'ai_pending_{domain}'
    next_id_key = f'ai_next_id_{domain}'
    if os.path.exists(fp):
        try:
            if BASE not in sys.path:
                sys.path.insert(0, BASE)
            from factor_generator.generator import RequirementInfo, FactorInfo
            data = json.load(open(fp))
            st.session_state[next_id_key] = data.get('next_id', 0)
            loaded = []
            for item in data.get('items', []):
                reqs = [RequirementInfo(**r) for r in item.get('fields_needed', [])]
                fi = FactorInfo(
                    name=item['name'], label=item.get('label', ''),
                    category=item.get('category', ''), domain=item.get('domain', ''),
                    formula=item.get('formula', ''),
                    dsl=item.get('dsl', ''),
                    code=item.get('code', ''),
                    raw=item.get('raw', False),
                    logic_summary=item.get('logic_summary', ''),
                    tables_needed=item.get('tables_needed', []),
                    fields_needed=reqs,
                )
                loaded.append({'id': item['id'], 'data': fi})
            st.session_state[ai_key] = loaded
        except Exception:
            st.session_state[ai_key] = []
    else:
        st.session_state[ai_key] = []
    st.session_state.setdefault(next_id_key, 0)


# ---- TOC 持久化（按 domain 独立存储）----

def _toc_file(domain):
    return os.path.join(BASE, 'output', f'toc_items_{domain}.json')


def _save_toc(domain):
    items = st.session_state.get(f'_toc_items_{domain}', [])
    os.makedirs(os.path.dirname(_toc_file(domain)), exist_ok=True)
    json.dump(items, open(_toc_file(domain), 'w'), ensure_ascii=False, indent=2)


def _load_toc(domain):
    toc_key = f'_toc_items_{domain}'
    if os.path.exists(_toc_file(domain)):
        try:
            st.session_state[toc_key] = json.load(open(_toc_file(domain)))
        except Exception:
            st.session_state[toc_key] = []
    else:
        st.session_state[toc_key] = []


def _set_toc_items(domain, items):
    st.session_state[f'_toc_items_{domain}'] = items
    _save_toc(domain)
