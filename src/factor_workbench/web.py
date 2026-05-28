"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run src/factor_workbench/web.py
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

st.set_page_config(page_title='因子测试', layout='wide')
st.title('因子测试')

st.markdown("""
<style>
    textarea[aria-label="运行日志"] { font-size: 12px !important; white-space: pre-wrap !important; word-break: break-all !important; }
    pre { white-space: pre-wrap !important; word-break: break-all !important; }
    .stPlotlyChart { margin-top: 40px; }
    [data-testid="stHeading"] { margin-top: 40px !important; }
    .stDataFrame thead th { text-align: center !important; }
    .block-container { max-width: 1400px; }
</style>
""", unsafe_allow_html=True)


csv_path = os.path.join(BASE, 'output/result/factor_summary.csv')

# 扫描所有 domain 的汇总表
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
    import ast
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
    import glob
    base = 'factors'
    for f in sorted(glob.glob(f'{BASE}/{base}/*.py')):
        if not os.path.exists(f):
            continue
        # domain 过滤：只搜 {domain}_factors.py
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


def _replace_factor(name, kind, code):
    """替换文件中的同名函数。优先搜索对应类型目录。"""
    func_code = _extract_func(code, name, kind)
    if not func_code:
        return
    import glob
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
    with open(os.path.join(BASE, f'{base_dir}/stock_{base_dir}.py'), 'a') as f:
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
    # 检查 domain 是否已配置（按约定规律生成路径，确保不会因不存在的 domain 造成误操作）
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



# ---- 因子搜索 ----
import pandas as pd

# 读所有 domain 的 CSV（如果有）
df = None
full_period = pd.DataFrame()
for _csv in _csv_files:
    _d = pd.read_csv(_csv)
    # 从文件名提取 domain，如 industry_factor_summary.csv → industry
    _domain = os.path.basename(_csv).replace('_factor_summary.csv', '')
    _d['domain'] = _domain
    df = pd.concat([df, _d]) if df is not None else _d
if df is not None and not df.empty:
    full_period = df[df['period'] == 'full'].copy()

# 构建因子索引：注册表（全量）+ CSV（补充统计值）
factor_index = {}
for _key, meta in _FACTORS.items():
    # _FACTORS key 格式: {domain}:{name}
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

# domain 筛选 + 批量运行
_domains = ['全部'] + sorted(all_factors['domain'].unique()) if 'domain' in all_factors.columns else ['全部']
_ds_cols = st.columns([3, 1])
with _ds_cols[0]:
    _selected = st.selectbox('领域', _domains, label_visibility='collapsed')
with _ds_cols[1]:
    with st.popover('批量运行'):
        _mode = st.radio('模式', ['skip', 'overwrite'], horizontal=True, key='batch_mode')

        # 按 domain 分组
        _dom_groups = {}
        _all_keys = []
        for _bk, _bm in sorted(_FACTORS.items()):
            _dom_groups.setdefault(_bm.domain, []).append((_bk, _bm))
            _all_keys.append(f'batch_f_{_bk}')

        # 全选（全部 domain）
        _gk = 'batch_all'
        if '_prev_' + _gk not in st.session_state:
            st.session_state['_prev_' + _gk] = False
        _g_cur = st.checkbox('全选所有领域', key=_gk)
        _g_prev = st.session_state['_prev_' + _gk]
        if _g_cur != _g_prev:
            for _t in _all_keys:
                st.session_state[_t] = _g_cur
        st.session_state['_prev_' + _gk] = _g_cur

        # 逐 domain 渲染
        _sel_factors = []
        for _dom, _items in sorted(_dom_groups.items()):
            _dom_targets = [f'batch_f_{_bk}' for _bk, _bm in _items]
            with st.expander(f'{_dom} ({len(_items)})', expanded=False):
                _dk = f'batch_dom_{_dom}'
                if '_prev_' + _dk not in st.session_state:
                    st.session_state['_prev_' + _dk] = False
                _d_cur = st.checkbox(f'全选 {_dom}', key=_dk)
                _d_prev = st.session_state['_prev_' + _dk]
                if _d_cur != _d_prev:
                    for _t in _dom_targets:
                        st.session_state[_t] = _d_cur
                st.session_state['_prev_' + _dk] = _d_cur
                for _bk, _bm in _items:
                    if st.checkbox(f'{_bm.name} ({_bm.label})', key=f'batch_f_{_bk}'):
                        _sel_factors.append(_bm)

        if st.button(f'执行 ({len(_sel_factors)} 个)'):
            import tempfile
            _log_lines = []
            for _meta in _sel_factors:
                _code = _get_func_code(_meta.name, 'factor', domain=_meta.domain)
                if not _code:
                    _log_lines.append(f'[{_meta.name}] 无代码')
                    continue
                _force = _mode == 'overwrite'
                _out, _err = _run_scratch(_code, force=_force)
                if _err:
                    _log_lines.append(f'[{_meta.name}] ❌ {_err[:800]}')
                else:
                    _log_lines.append(f'[{_meta.name}] ✅')
            st.session_state.ai_log = '\n'.join(_log_lines)
            st.rerun()

_domain_filter = all_factors['domain'] == _selected if _selected != '全部' else pd.Series([True] * len(all_factors))

_c1, _c2 = st.columns([4, 1])
with _c1:
    with st.form(key='search_form', border=False):
        _cols = st.columns([3, 1])
        with _cols[0]:
            q = st.text_input('🔍 搜索因子', placeholder='输入因子名、中文名或分类...',
                             label_visibility='collapsed', key='search_input')
        with _cols[1]:
            submitted = st.form_submit_button('搜索', use_container_width=True)
            if submitted:
                st.session_state.mode = 'search'
with _c2:
    _cols = st.columns([3, 1])
    with _cols[0]:
        if st.button('因子列表', width='stretch'):
            st.session_state.mode = 'list'
    with _cols[1]:
        if st.button('↻', help='同步 .py 文件的变更'):
            _FACTORS.clear()
            load_factor_modules(['factors'])
            st.rerun()

mode = st.session_state.get('mode', '')
q_lower = q.lower() if q else ''

# ---- 搜索模式 ----
if mode == 'search' and q_lower:
    matched = all_factors[
        _domain_filter &
        (all_factors['factor'].str.lower().str.contains(q_lower, na=False) |
         all_factors['label'].str.lower().str.contains(q_lower, na=False) |
         all_factors['cat'].str.lower().str.contains(q_lower, na=False))
    ]
    if not matched.empty:
        st.caption(f'搜索列表  共 {matched["factor"].nunique()} 个因子')
        show = matched[disp_cols].copy()
        show.columns = [_disp_labels[c] for c in disp_cols]
        for c in ['多头胜率']:
            if c in show.columns:
                show[c] = show[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
        event = st.dataframe(show, hide_index=True, width='stretch',
                             column_config={c: st.column_config.TextColumn(c, alignment='center') for c in show.columns},
                             on_select='rerun', selection_mode='single-row',
                             key=f'search_tbl_{st.session_state.get("search_key", "")}')
        if event and event.selection and event.selection.rows:
            idx = event.selection.rows[0]
            _sel_row = matched.iloc[idx]
            selected_name = _sel_row['factor']
            selected_domain = _sel_row.get('domain', '')
            _prev = st.session_state.get('_sel', '')
            st.session_state._sel = selected_name
            st.session_state.last_names = [(selected_name, 'factor', selected_domain)]
            if selected_name != _prev:
                st.session_state.should_scroll = True
    else:
        st.caption(f'未找到含 "{q}" 的因子')

# ---- 列表模式 ----
if mode == 'list':
    all_show = all_factors[_domain_filter][disp_cols].copy()
    all_show = all_show.sort_values('factor')
    all_show.columns = [_disp_labels[c] for c in disp_cols]
    for c in ['多头胜率']:
        if c in all_show.columns:
            all_show[c] = all_show[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
    st.caption(f'因子列表  共 {all_show["因子名"].nunique()} 个因子')
    ev = st.dataframe(all_show, hide_index=True, width='stretch', height=400,
                     column_config={c: st.column_config.TextColumn(c, alignment='center') for c in all_show.columns},
                     on_select='rerun', selection_mode='single-row',
                     key=f'all_tbl_{st.session_state.get("search_key", "")}')
    if ev and ev.selection and ev.selection.rows:
        idx = ev.selection.rows[0]
        _all_names = all_show['因子名'].tolist()
        if idx < len(_all_names):
            _prev = st.session_state.get('_sel', '')
            st.session_state._sel = _all_names[idx]
            _a_row = all_show.iloc[idx]
            st.session_state.last_names = [(_all_names[idx], 'factor', _a_row.get('领域', ''))]
            if _all_names[idx] != _prev:
                st.session_state.should_scroll = True

# ---- AI 因子生成 ----
_AI_FILE = os.path.join(BASE, 'output', 'ai_pending.json')

def _save_ai():
    data = {
        'next_id': st.session_state.ai_next_id,
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
        } for p in st.session_state.ai_pending],
    }
    os.makedirs(os.path.dirname(_AI_FILE), exist_ok=True)
    json.dump(data, open(_AI_FILE, 'w'), ensure_ascii=False, indent=2)




# ── 配置驱动的展示映射 ──────────────────────────────

MULTI_CHARTS = {'ic_distribution'}

CHART_MAP = {
    'ic_cumulative': (load_ic_data, render_ic_cumulative),
    'ic_distribution': (load_ic_data, render_ic_distribution),
    'long_short': (load_ret_data, render_long_short),
    'decile_bar': (load_ret_data, render_decile_bar),
    'win_rate': (load_ret_data, render_win_rate),
    # 多调仓期 decile 图（suffix 对应 groups.run_decile 的 horizons）
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

# 指标格式化在 chart_renderer._METRIC_FMT 中定义

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


def _refresh_data():
    """重新扫描数据，更新 pending 因子的字段可用性。"""
    subprocess.run([sys.executable, 'scripts/scan_schema.py'], cwd=BASE, capture_output=True)
    dd_path = os.path.join(BASE, 'factor_generator/config/data_dictionary.json')
    if not os.path.exists(dd_path):
        return
    data_dict = json.load(open(dd_path))
    # 同步 FIELD_MAP
    from factor_generator.dsl_grammar import sync_field_map
    sync_field_map(data_dict)
    valid = {}
    for t in data_dict.get('tables', [],):
        valid[t['name']] = {f['name'] for f in t.get('fields', [])}
    for item in st.session_state.ai_pending:
        for r in item['data'].fields_needed:
            r.status = 'available' if (valid.get(r.table) and r.field in valid[r.table]) else 'missing'
    _save_ai()

def _load_ai():
    if os.path.exists(_AI_FILE):
        try:
            if BASE not in sys.path:
                sys.path.insert(0, BASE)
            from factor_generator.generator import RequirementInfo, FactorInfo
            data = json.load(open(_AI_FILE))
            st.session_state.ai_next_id = data.get('next_id', 0)
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
            st.session_state.ai_pending = loaded
        except Exception as e:
            st.session_state.ai_pending = []
    else:
        st.session_state.ai_pending = []
    st.session_state.setdefault('ai_next_id', 0)

_load_ai()

_TOC_FILE = os.path.join(BASE, 'output', 'toc_items.json')


def _save_toc():
    items = st.session_state.get('_toc_items', [])
    os.makedirs(os.path.dirname(_TOC_FILE), exist_ok=True)
    json.dump(items, open(_TOC_FILE, 'w'), ensure_ascii=False, indent=2)


def _load_toc():
    if os.path.exists(_TOC_FILE):
        try:
            st.session_state['_toc_items'] = json.load(open(_TOC_FILE))
        except Exception:
            st.session_state['_toc_items'] = []
    else:
        st.session_state['_toc_items'] = []


def _set_toc_items(items):
    st.session_state['_toc_items'] = items
    _save_toc()


_load_toc()

with st.expander('AI 因子生成'):
    st.session_state.setdefault('ai_log', '')
    _c_log = st.columns([3, 2])
    with _c_log[0]:
        report_text = st.text_area('研报内容', height=400, label_visibility='collapsed',
                                    placeholder='粘贴研报或因子想法...')
        _has_report = bool(report_text.strip())
        _gen_clicked = st.button('生成', key='ai_generate', disabled=not _has_report)
        _toc_clicked = st.button('生成目录', key='ai_toc', disabled=not _has_report)
    with _c_log[1]:
        _ai_log = st.session_state.get('ai_log', '')
        st.text_area('日志', _ai_log, height=400, disabled=True, label_visibility='collapsed')
    st.markdown('<style>div:has(> textarea[aria-label="日志"]) textarea{font-size:13px!important;white-space:pre-wrap!important;word-break:break-all!important}</style>', unsafe_allow_html=True)

    if _gen_clicked:
        st.session_state.ai_gen_count = st.session_state.get('ai_gen_count', 0) + 1
        if st.session_state.get('ai_log', ''):
            st.session_state.ai_log = ''
            st.session_state._gen_ready = True
            st.rerun()
        else:
            st.session_state._gen_ready = True

    # ── TOC 生成 ──
    if _toc_clicked:
        st.session_state._toc_pending = True
        st.rerun()
    if st.session_state.pop('_toc_pending', False):
        with st.spinner('提取因子目录...'):
            from factor_generator import generate_toc
            try:
                _r = generate_toc(report_text)
            except Exception as _exc:
                st.error(f'目录生成失败: {_exc}')
                _r = None
            if _r and _r.error:
                st.error(_r.error)
            elif _r and _r.factors:
                _existing = st.session_state.get('_toc_items', [])
                _existing_names = {x['name'] for x in _existing}
                _new_items = [
                    {'name': f.name, 'label': f.label, 'domain': f.domain,
                     'logic_summary': f.logic_summary}
                    for f in _r.factors if f.name not in _existing_names
                ]
                if _new_items:
                    _set_toc_items(_existing + _new_items)
                st.toast(f'提取 {len(_r.factors)} 个因子，新增 {len(_new_items)} 个', icon='📋')
                if _r.usage:
                    u = _r.usage
                    st.session_state.ai_log = f'目录: {len(_r.factors)} 个因子，消耗 {u.get("total_tokens","-")} tokens'
                st.rerun()

    if st.session_state.pop('_gen_ready', False):
        with st.spinner('LLM 分析中...'):
            import sys as _sys
            if BASE not in _sys.path:
                _sys.path.insert(0, BASE)
            from factor_generator import generate
            try:
                _r = generate(report_text)
            except Exception as _exc:
                st.error(f'生成失败: {_exc}')
                _r = None
            if _r and _r.error:
                st.error(_r.error)
            elif _r:
                for _fi in _r.factors:
                    _id = st.session_state.ai_next_id
                    st.session_state.ai_next_id += 1
                    st.session_state.ai_pending.insert(0, {
                        'id': _id, 'data': _fi,
                    })
                st.session_state.ai_pending_sel = st.session_state.ai_pending[0]['id']
                _save_ai()
                _rlog = _r.raw_llm_output or {}
                _rtext = json.dumps(_rlog, ensure_ascii=False, indent=2) if _rlog else ''
                st.session_state.ai_log = (
                    f'生成 {len(_r.factors)} 个因子\n'
                    + '\n'.join(f'  [{f.domain}] {f.name} — {f.label}' for f in _r.factors)
                    + (f'\n\n--- LLM 原始输出 ---\n{_rtext[:10000]}' if _rtext else '')
                    + (f'\n\n用量: {_r.usage}' if _r.usage else ''))
                if _r.usage:
                    u = _r.usage
                    st.toast(f'生成 {len(_r.factors)} 个因子，消耗 {u.get("total_tokens","-")} tokens', icon='🤖')
        st.rerun()

if st.session_state.get('ai_gen_count', 0):
    st.caption(f'生成运行: {st.session_state.ai_gen_count} 次')
_pending = st.session_state.ai_pending
if _pending:
    st.markdown(f'**待处理因子 ({len(_pending)})**')
    _id2label = {p['id']: f"[{p['data'].name}] {p['data'].label}" for p in _pending}
    _sel_id = st.selectbox('选择因子', list(_id2label.keys()),
                            format_func=lambda i: _id2label[i], key='ai_pending_sel')
    _item = next(p for p in _pending if p['id'] == _sel_id)
    _fi = _item['data']

    # 查重（按 name + domain）
    _existing = get_factors(domain=_fi.domain).get(_fi.name)
    if _existing:
        st.warning(f'同名因子 {_fi.name} 已存在于 {_fi.domain} domain')

    # 展示 DSL / formula / 代码
    if _fi.dsl:
        st.markdown(f'```\n{_fi.dsl}\n```')
    elif _fi.formula:
        _formatted = sqlparse.format(_fi.formula, reindent=True, keyword_case='upper', indent_width=4)
        st.markdown(f'```sql\n{_formatted}\n```')
    elif _fi.code:
        st.code(_fi.code, language='python')

    # 数据需求状态
    _all_ok = all(r.status == 'available' for r in _fi.fields_needed)
    for r in _fi.fields_needed:
        tag = '✅' if r.status == 'available' else '❌'
        dest = f' → {r.table}.{r.field}' if r.table else ''
        st.markdown(f'{tag} {r.field}{dest}')

    # 编译后代码展示（raw 模式直接展示，DSL/formula 需点击编译后展示）
    _compiled_key = f'ai_compiled_{_sel_id}'
    _needs_compile = bool(_fi.dsl or _fi.formula)  # 有源码就需要编译
    _already_compiled = st.session_state.get(_compiled_key, False)
    # DSL 因子的 code 在生成时已预编译，但只显示到用户点击编译之后
    if _fi.code and (not _fi.dsl or _already_compiled):
        st.code(_fi.code, language='python')

    _btn_cols = st.columns([1, 2, 3, 1])
    # ── 编译（有源码时可用，纯展示型原始代码禁用）──
    with _btn_cols[0]:
        if _needs_compile:
            if st.button('编译', key=f'ai_compile_{_sel_id}'):
                from factor_generator.compiler import compile_factor
                try:
                    _fi.code = compile_factor(_fi)
                    st.session_state[_compiled_key] = True
                    _save_ai()
                except Exception as _e:
                    st.error(f'编译失败: {_e}')
                st.rerun()
        else:
            st.button('编译', disabled=True, key=f'ai_compile_{_sel_id}')
    # ── 刷新数据 ──
    with _btn_cols[1]:
        if st.button('刷新数据', help='重新扫描数据目录，更新字段可用性'):
            _refresh_data()
            st.rerun()
    # ── 运行 + 选项（已编译 或 无需编译的原始代码）──
    _can_run = _already_compiled or (_fi.code and not _needs_compile)
    _ai_force = False
    def _toggle_ai():
        if st.session_state.ai_force and st.session_state.ai_replace:
            st.session_state.ai_replace = False
    def _toggle_ai2():
        if st.session_state.ai_replace and st.session_state.ai_force:
            st.session_state.ai_force = False
    if _all_ok and _can_run:
        with _btn_cols[2]:
            _c = st.columns([1, 1, 1])
            _ai_force = _c[0].checkbox('覆盖重算', key='ai_force', on_change=_toggle_ai)
            _ai_replace = _c[1].checkbox('覆盖写入', key='ai_replace', on_change=_toggle_ai2)
            if _c[2].button('运行', key='ai_run'):
                _stdout, _stderr = _run_scratch(_fi.code, force=_ai_force or _ai_replace)
                st.session_state.log = _stdout
                if _stderr:
                    st.session_state.log += '\n--- 错误 ---\n' + _stderr
                if _ai_replace and _stdout and '完成' in _stdout:
                    _replace_factor(_fi.name, 'factor', _fi.code)
                _FACTORS.clear()
                load_factor_modules(['factors'])
                st.session_state.last_names = [(_fi.name, 'factor', _fi.domain)]
                st.session_state.should_scroll = True
                st.session_state.ai_pending = [p for p in _pending if p['id'] != _sel_id]
                _save_ai()
                st.rerun()
    # ── 删除 ──
    with _btn_cols[3]:
        if st.button('删除', key='ai_del'):
            st.session_state.ai_pending = [p for p in _pending if p['id'] != _sel_id]
            _save_ai()
            st.rerun()

    # ── 全部运行弹窗 ──
    with st.popover(f'全部运行 ({len(_pending)})'):
        _non_dup_ids = [p['id'] for p in _pending if not get_factors(domain=p['data'].domain).get(p['data'].name)]
        _gk = 'ai_batch_all'
        if '_prev_' + _gk not in st.session_state:
            st.session_state['_prev_' + _gk] = False
        _g_cur = st.checkbox('全选', key=_gk, disabled=not _non_dup_ids)
        _g_prev = st.session_state['_prev_' + _gk]
        if _g_cur != _g_prev:
            for _pid in _non_dup_ids:
                st.session_state[f'ai_batch_{_pid}'] = _g_cur
        st.session_state['_prev_' + _gk] = _g_cur
        # 按 domain 分组
        _dom_pending = {}
        for _p in _pending:
            _dom_pending.setdefault(_p['data'].domain, []).append(_p)
        _run_ids = []
        for _dom, _items in sorted(_dom_pending.items()):
            _non_dup_items = [p for p in _items if p['id'] in _non_dup_ids]
            if not _non_dup_items:
                continue
            with st.expander(f'{_dom} ({len(_non_dup_items)})', expanded=False):
                _dk = f'ai_dom_{_dom}'
                _dc = st.checkbox(f'全选 {_dom}', key=_dk)
                _dp = st.session_state.get('_prev_' + _dk, False)
                if _dc != _dp:
                    for _p in _non_dup_items:
                        st.session_state[f'ai_batch_{_p["id"]}'] = _dc
                st.session_state['_prev_' + _dk] = _dc
                for _p in _items:
                    _is_dup = _p['id'] not in _non_dup_ids
                    _checked = st.checkbox(
                        f'{_p["data"].name} — {_p["data"].label}',
                        key=f'ai_batch_{_p["id"]}', disabled=_is_dup)
                    if _checked and not _is_dup:
                        _run_ids.append(_p['id'])
        if st.button(f'运行选中 ({len(_run_ids)})'):
            from factor_generator.compiler import compile_factor
            msgs = []
            for _rid in _run_ids:
                _item = next(p for p in _pending if p['id'] == _rid)
                _fi = _item['data']
                try:
                    _code = compile_factor(_fi)
                    _out, _err = _run_scratch(_code, force=True)
                    if _err:
                        msgs.append(f'[{_fi.name}] ❌ {_err[:200]}')
                    else:
                        msgs.append(f'[{_fi.name}] ✅')
                except Exception as _e:
                    msgs.append(f'[{_fi.name}] ❌ {_e}')
            st.session_state.ai_log = '\n'.join(msgs)
            st.rerun()

    # ── 重复处理弹窗 ──
    _dup_list = [p for p in _pending if get_factors(domain=p['data'].domain).get(p['data'].name)]
    if _dup_list:
        # 弹窗关闭时标记重置，下次打开时清除 text_input 记忆
        _pop_st = st.session_state.get('dupe_popover', {})
        _pop_open = isinstance(_pop_st, dict) and _pop_st.get('is_open', False)
        _pop_was = st.session_state.get('_pop_was', False)
        if not _pop_open and _pop_was:
            st.session_state['_dupe_reset'] = True
        st.session_state['_pop_was'] = _pop_open

        with st.popover(f'重复处理 ({len(_dup_list)})', key='dupe_popover'):
            if st.session_state.pop('_dupe_reset', False):
                for _p in _dup_list:
                    st.session_state.pop(f'dupe_name_{_p["id"]}', None)
            _dup_doms = {}
            for _p in _dup_list:
                _dup_doms.setdefault(_p['data'].domain, []).append(_p)
            for _dom, _items in sorted(_dup_doms.items()):
                with st.expander(f'⚠️ {_dom} ({len(_items)})', expanded=False):
                    for _p in _items:
                        _fi = _p['data']
                        st.markdown(f'**{_fi.name}** 待办因子:')
                        _formatted = sqlparse.format(_fi.formula, reindent=True, keyword_case='upper', indent_width=4)
                        st.code(_formatted, language='sql')
                        _existing_code = _get_func_code(_fi.name, 'factor', domain=_fi.domain)
                        if _existing_code:
                            st.caption('已存在:')
                            st.code(_existing_code, language='python')
                        _new_name = st.text_input('新名称', value=_fi.name, key=f'dupe_name_{_p["id"]}')
                        _name_changed = _new_name != _fi.name
                        _name_dup = _name_changed and bool(get_factors(domain=_fi.domain).get(_new_name))
                        _name_empty = _name_changed and not _new_name.strip()
                        if _name_dup:
                            st.warning(f'名称 {_new_name} 已被占用')
                        if _name_empty:
                            st.warning('名称不能为空')
                        _do_overwrite = st.checkbox('覆盖已有因子', key=f'dupe_over_{_p["id"]}')
                        _can_rename = _name_changed and not _name_dup and not _name_empty
                        cols_act = st.columns(3)
                        if _can_rename:
                            if cols_act[0].button('确认改名', key=f'dupe_rename_{_p["id"]}'):
                                _fi.name = _new_name
                                _save_ai()
                                st.rerun()
                        if cols_act[1].button('覆盖并运行', key=f'dupe_over_run_{_p["id"]}', disabled=not _do_overwrite):
                            from factor_generator.compiler import compile_factor
                            try:
                                _code = compile_factor(_fi)
                                _out, _err = _run_scratch(_code, force=True)
                                if _err:
                                    st.session_state.ai_log = f'[{_fi.name}] ❌ {_err[:200]}'
                                else:
                                    _replace_factor(_fi.name, 'factor', _code)
                                    st.session_state.ai_log = f'[{_fi.name}] ✅'
                            except Exception as _e:
                                st.session_state.ai_log = f'[{_fi.name}] ❌ {_e}'
                            st.rerun()
                        if cols_act[2].button('删除待办', key=f'dupe_del_{_p["id"]}'):
                            st.session_state.ai_pending = [x for x in st.session_state.ai_pending if x['id'] != _p['id']]
                            _save_ai()
                            st.rerun()
    # ── TOC 目录展示与批量生成 ──
    _toc_items = st.session_state.get('_toc_items', [])
    if _toc_items:
        with st.expander(f'因子目录 ({len(_toc_items)})', expanded=False):
            _toc_cols = st.columns([2, 2, 1, 1])
            _toc_sel_all = _toc_cols[0].checkbox('全选', key='toc_sel_all')
            # 全选状态变化时同步所有子选项
            if _toc_sel_all != st.session_state.get('_prev_toc_sel_all', False):
                for _item in _toc_items:
                    st.session_state[f'toc_{_item["name"]}'] = _toc_sel_all
            st.session_state['_prev_toc_sel_all'] = _toc_sel_all
            _toc_selected = []
            for _item in _toc_items:
                _cols = st.columns([2, 2, 1, 1])
                _checked = _cols[0].checkbox(_item['name'], value=False, key=f'toc_{_item["name"]}')
                _cols[1].write(_item['label'])
                _cols[2].write(_item['domain'])
                _cols[3].write(_item.get('logic_summary', '')[:30])
                if _checked:
                    _toc_selected.append(_item)
            if _toc_selected:
                _batch_size = st.slider('每批数量', 1, 10, 5, key='toc_batch_size')
                if st.button(f'批量生成 ({len(_toc_selected)} 个)'):
                    _bs = st.session_state.get('toc_batch_size', 5)
                    _total = len(_toc_selected)
                    _msgs = []
                    for _i in range(0, _total, _bs):
                        _batch = _toc_selected[_i:_i+_bs]
                        _names = [x['name'] for x in _batch]
                        _prompt = f'请生成以下因子的完整 SQL 公式:\n'
                        for _x in _batch:
                            _prompt += f'  - {_x["name"]} ({_x["label"]}): {_x.get("logic_summary", "")}\n'
                        _prompt += f'\n研报原文:\n{report_text}'
                        try:
                            from factor_generator import generate
                            _r = generate(_prompt)
                            if _r and not _r.error and _r.factors:
                                for _fi in _r.factors:
                                    _id = st.session_state.ai_next_id
                                    st.session_state.ai_next_id += 1
                                    st.session_state.ai_pending.insert(0, {'id': _id, 'data': _fi})
                                _save_ai()
                                _msgs.append(f'批 {_i//_bs+1}/{(len(_toc_selected)-1)//_bs+1}: {" ".join(_names)} ✅')
                            else:
                                _msgs.append(f'批 {_i//_bs+1}: {" ".join(_names)} ❌ {_r.error if _r else "空结果"}')
                        except Exception as _exc:
                            _msgs.append(f'批 {_i//_bs+1}: {" ".join(_names)} ❌ {_exc}')
                    st.session_state.ai_log = '\n'.join(_msgs)
                    # 仅移除已处理的项，未处理项保留
                    _processed_names = {x['name'] for x in _toc_selected}
                    _remaining = [x for x in st.session_state['_toc_items']
                                  if x['name'] not in _processed_names]
                    if _remaining:
                        _set_toc_items(_remaining)
                    else:
                        _set_toc_items([])
                    st.rerun()
            _toc_cols = st.columns([1, 1])
            if _toc_cols[0].button('清空目录'):
                _set_toc_items([])
                st.rerun()

    # ── 数据需求汇总 ──
    with st.expander('数据需求汇总'):
        _summary = _build_req_summary(_pending)
        if not _summary:
            st.caption('无数据需求信息')
        else:
            _total_missing = 0
            for table_name, fields in sorted(_summary.items()):
                _table_ok = all(f['status'] == 'available' for f in fields)
                tag = '✅' if _table_ok else '❌'
                st.markdown(f'**{tag} {table_name}**')
                for info in fields:
                    f_tag = '✅' if info['status'] == 'available' else '❌'
                    if info['status'] != 'available':
                        _total_missing += 1
                    _count = len(info['needed_by'])
                    _names = ', '.join(info['needed_by'])
                    st.markdown(f'&nbsp;&nbsp;{f_tag} {info["field"]} — {_count} 个因子（{_names}）')
            if _total_missing:
                st.caption(f'共 {_total_missing} 个字段缺失，补全数据后点"刷新数据"更新状态')

col_left, col_right = st.columns([3, 2])

with col_left:
    st.caption('代码')
    _result = code_editor(TEMPLATE, lang='python', height='420px', key='factor_code_v1',
                          response_mode=['blur', 'debounce'],
                          options={'showInvisibles': False, 'minimap': {'enabled': False}})
    code = _result.get('text') or TEMPLATE
    c1, c2, c3 = st.columns(3)
    with c1:
        force = st.checkbox('覆盖重算', key='editor_force', on_change=lambda: (
            st.session_state.update(editor_replace=False) if st.session_state.editor_force and st.session_state.editor_replace else None))
    with c2:
        replace = st.checkbox('覆盖写入', key='editor_replace', on_change=lambda: (
            st.session_state.update(editor_force=False) if st.session_state.editor_replace and st.session_state.editor_force else None))
    with c3:
        run = st.button('运行', width='stretch')

with col_right:
    st.caption('运行日志')
    log_text = st.session_state.get('log', '')
    st.text_area('运行日志', log_text, height=420, label_visibility='collapsed', disabled=True)

# ---- 运行流程 ----
if run:
    st.session_state.replace_pending = replace
    st.session_state.log = ''
    st.session_state.last_names = []
    st.session_state.pending = True
    st.session_state.search_key = str(hash(str(time.time())))
    st.rerun()

if st.session_state.get('pending'):
    # 语法检查
    try:
        ast.parse(code)
    except SyntaxError as e:
        st.session_state.log = f'语法错误: 第{e.lineno}行 {e.msg}'
        st.session_state.pending = False
        st.rerun()

    with st.spinner('计算中...'):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(code)
        tmp_path = tmp.name
        tmp.close()
        env = os.environ.copy()
        env['PYTHONPATH'] = f'{os.path.join(BASE, "src")}:{env.get("PYTHONPATH", "")}'
        cmd = [sys.executable, '-m', 'factor_workbench.scratch']
        if force or replace:
            cmd.append('--force')
        cmd.append(tmp_path)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, env=env)
        os.unlink(tmp_path)

        # pipeline 跑成功后才执行代码替换
        if result.returncode == 0 and st.session_state.pop('replace_pending', False):
            items = _parse_decorators(code)
            for _name, _kind, _dom in items:
                _replace_factor(_name, _kind, code)

    st.session_state.pending = False
    st.session_state.log = result.stdout
    if result.stderr:
        st.session_state.log += '\n--- 错误 ---\n' + result.stderr
    st.session_state.last_names = _parse_decorators(code)
    st.session_state.should_scroll = True
    st.rerun()

st.markdown('<div id="factor-metrics"></div>', unsafe_allow_html=True)

# ---- 展示选中因子的函数代码 + 删除 ----
_last = st.session_state.get('last_names', [])
if _last:
    for _name, _kind, _dom in _last:
        from factor_workbench.engine.registry import get_factor as _gf
        _meta_fc = _gf(_name, _dom) if _dom else get_factors().get(_name)
        _found = _get_func_code(_name, _kind, domain=_dom or (_meta_fc.domain if _meta_fc else None))
        if _found:
            _bar = st.columns([20, 1])
            with _bar[1]:
                with st.popover('⋮'):
                    if st.button('删除', key=f'del_{_name}'):
                        _delete_factor(_name, _dom)
                        st.rerun()
            st.code(_found, language='python')

# ---- 显示结果 ----
names = st.session_state.get('last_names', [])

if names:
    # 标题由 layout 中 _title: 项控制

    # 指标行（从 CSV，按 domain 配置展示）
    for name, _, _ in names:
        pass
# (metrics handled by layout above)

    # 指标展示表（按 layout 配置）
    if df is not None and not df.empty and names:
        from factor_workbench.engine.registry import get_factor as _gf
        _tbl_name, _tbl_kind, _tbl_dom = names[0]
        _tbl_meta = _gf(_tbl_name, _tbl_dom) if _tbl_dom else get_factors().get(_tbl_name)
        if _tbl_meta:
            from config.domain_config import DOMAIN_CONFIG
            _tbl_dc = DOMAIN_CONFIG.get(_tbl_meta.domain, {})
            _tbl_layout = _tbl_dc.get('display', {}).get('layout', [])
            if any('_table' in row for row in _tbl_layout):
                _tbl_metrics = _tbl_dc.get('display', {}).get('metrics', [])
                html = render_metrics_table(df, names, _tbl_metrics)
                if html:
                    st.markdown(html, unsafe_allow_html=True)

    # 因子展示：按 layout 逐行渲染
    for name, kind, dom in names:
        from factor_workbench.engine.registry import get_factor as _gf
        meta = _gf(name, dom) if dom else get_factors().get(name)
        if not meta:
            continue
        cat = meta.category
        domain = meta.domain
        func_code = _get_func_code(name, kind, domain=domain)
        _rebuild = [df is None or df[df['factor'] == name].empty]

        from config.domain_config import DOMAIN_CONFIG
        _dc = DOMAIN_CONFIG.get(domain, {})
        _layout = _dc.get('display', {}).get('layout', [])

        for row in _layout:
            if not row:
                continue
            item = row[0]

            # 标题行
            if item and isinstance(item, str) and item.startswith('_title:'):
                st.subheader(item[7:])

            # _table 和 _comparison 跨因子，在循环外统一处理
            elif item in ('_table', '_comparison'):
                pass

            # 多图展开行（ic_distribution 等）
            elif len(row) == 1 and item in MULTI_CHARTS:
                entry = CHART_MAP.get(item)
                if entry is None:
                    continue
                load_fn, render_fn = entry
                try:
                    data = load_fn(BASE, name, cat, domain=domain)
                    if data is not None:
                        figs = render_fn(data)
                        cols = st.columns(len(figs))
                        for (h, fig), col in zip(figs, cols):
                            with col:
                                st.plotly_chart(fig, width='stretch', key=f'{name}_{item}_{h}')
                    else:
                        _rebuild[0] = True
                except Exception:
                    _rebuild[0] = True

            # 普通图行
            else:
                cols = st.columns(len(row))
                for j, c_name in enumerate(row):
                    entry = CHART_MAP.get(c_name)
                    if entry is None:
                        continue
                    load_fn, render_fn = entry
                    with cols[j]:
                        try:
                            data = load_fn(BASE, name, cat, domain=domain)
                            if data is not None:
                                fig = render_fn(data, name)
                                _label = re.search(r'_T(\d+)$', c_name)
                                if _label:
                                    cur = fig.layout.title.text
                                    fig.update_layout(title=f"{cur}（持有{_label.group(1)}日）")
                                st.plotly_chart(fig, width='stretch', key=f'{name}_{c_name}')
                            else:
                                _rebuild[0] = True
                        except Exception:
                            _rebuild[0] = True

        # 补全数据按钮
        if _rebuild[0] and func_code:
            st.info(f'{name} 部分分析数据缺失')
            if st.button('补全数据', key=f'rebuild_{name}'):
                with st.spinner('计算中...'):
                    stdout, stderr = _run_scratch(func_code, force=True)
                    st.session_state.log = stdout
                    if stderr:
                        st.session_state.log += '\n--- 错误 ---\n' + stderr
                    st.rerun()

    # scroll
    if st.session_state.pop('should_scroll', False):
        st.html("""
        <script>document.getElementById('factor-metrics').scrollIntoView({behavior:'smooth',block:'start'})</script>
        <span style="display:none">""" + str(hash(str(st.session_state.get('_sc', 0)))) + """</span>
        """, unsafe_allow_javascript=True)
        st.session_state._sc = st.session_state.get('_sc', 0) + 1
