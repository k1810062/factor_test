"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run src/factor_workbench/web.py
"""

import ast, time
import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob, shutil, numpy as np
from code_editor import code_editor

from factor_workbench.analysis.chart_renderer import (
    load_ic_data, load_ret_data,
    render_ic_cumulative, render_long_short,
    render_decile_bar, render_win_rate, render_ic_distribution,
)
from factor_workbench.engine.registry import get_factors, load_factor_modules, _FACTORS, _FEATURES
from pathlib import Path
from factor_workbench.analysis.auto_config import generate_config

BASE = str(Path(__file__).resolve().parent.parent.parent)  # llm_factors/
generate_config()
load_factor_modules(['factors', 'features'])

st.set_page_config(page_title='因子测试', layout='wide')
st.title('因子测试')

st.markdown("""
<style>
    textarea[aria-label="运行日志"] { font-size: 12px !important; }
    .stPlotlyChart { margin-top: 40px; }
    [data-testid="stHeading"] { margin-top: 40px !important; }
    .stDataFrame thead th { text-align: center !important; }
    .block-container { max-width: 1400px; }
</style>
""", unsafe_allow_html=True)


csv_path = os.path.join(BASE, 'output/result/factor_summary.csv')

# 扫描所有 domain 的汇总表
_csv_files = sorted(glob.glob(os.path.join(BASE, 'output/result/*_factor_summary.csv')))

TEMPLATE = '''@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / lag(close, 5) OVER w - 1) as ret_5d
        FROM industry_daily
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)
'''


def _find_func(txt, name):
    """在文件中查找 @factor 或 @feature 函数，返回 (start, end) 或 None。"""
    decors = [f"@factor(name='{name}'", f"@feature(name='{name}'"]
    for d in decors:
        i = txt.find(d)
        if i >= 0:
            nxt = txt.find('\n@factor(', i + 1)
            if nxt < 0:
                nxt = txt.find('\n@feature(', i + 1)
            if nxt < 0:
                nxt = txt.find('\nfrom ', i + 1)
            if nxt < 0:
                nxt = len(txt)
            return i, nxt
    return None


def _parse_decorators(code):
    """从代码中提取 (name, kind) 列表。识别所有 @xxx(name=...) 格式。"""
    import ast
    tree = ast.parse(code)
    items = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            dec = node.decorator_list[0]
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                name = next((ast.literal_eval(kw.value) for kw in dec.keywords if kw.arg == 'name'), None)
                if name:
                    items.append((name, dec.func.id))
    return items



def _get_func_code(name, kind):
    """从对应类型目录提取函数代码。"""
    import glob
    base = 'features' if kind == 'feature' else 'factors'
    for f in sorted(glob.glob(f'{BASE}/{base}/*.py')):
        if not os.path.exists(f):
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
    for k in ('factor', 'feature', 'metric'):
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


def _delete_factor(name):
    """从 .py 文件、因子库、分析结果中彻底删除一个因子。"""
    meta = get_factors().get(name)
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
    _paths = {
        'stock': 'output/factor_library/stock_factors.parquet',
        'industry': 'output/factor_library/industry_factors.parquet',
        'industry_monthly': 'output/factor_library/industry_monthly_factors.parquet',
    }
    fp = _paths.get(domain)
    if fp and os.path.exists(fp):
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
    _FEATURES.clear()
    load_factor_modules(['factors', 'features'])
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
for name, meta in get_factors().items():
    factor_index[name] = {
        'factor': name, 'label': meta.label,
        'cat': meta.category, 'domain': meta.domain,
    }
if not full_period.empty:
    for _, row in full_period.iterrows():
        fname = row['factor']
        if fname in factor_index:
            for col in row.index:
                if col not in ('factor', 'label', 'cat', 'period'):
                    factor_index[fname][col] = row[col]

all_factors = pd.DataFrame(list(factor_index.values()))
_disp_labels = {
    'factor': '因子名', 'label': '标签', 'cat': '分类',
    'ic_T1': 'IC均值', 'icir_T1': 'ICIR',
    'long_win': '多头胜率', 'kurtosis': '峰度',
}
disp_cols = [c for c in _disp_labels if c in all_factors.columns]

# domain 筛选
_domains = ['全部'] + sorted(all_factors['domain'].unique()) if 'domain' in all_factors.columns else ['全部']
_selected = st.selectbox('领域', _domains, label_visibility='collapsed')
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
            st.session_state.should_scroll = True
    with _cols[1]:
        if st.button('↻', help='同步 .py 文件的变更'):
            _FACTORS.clear()
            _FEATURES.clear()
            load_factor_modules(['factors', 'features'])
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
            selected_name = matched.iloc[idx]['factor']
            _prev = st.session_state.get('_sel', '')
            st.session_state._sel = selected_name
            st.session_state.last_names = [(selected_name, 'factor')]
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
            st.session_state.last_names = [(_all_names[idx], 'factor')]
            if _all_names[idx] != _prev:
                st.session_state.should_scroll = True

# ---- AI 因子生成 ----
_AI_FILE = os.path.join(BASE, 'output', 'ai_pending.json')

def _save_ai():
    data = {
        'next_id': st.session_state.ai_next_id,
        'items': [{
            'id': p['id'], 'name': p['data'].name, 'label': p['data'].label,
            'category': p['data'].category, 'domain': p['data'].domain,
            'code': p['data'].code, 'logic_summary': p['data'].logic_summary,
            'requirements': [
                {'description': r.description, 'status': r.status,
                 'matched_table': r.matched_table, 'matched_field': r.matched_field,
                 'confidence': r.confidence}
                for r in p['data'].data_requirements
            ],
        } for p in st.session_state.ai_pending],
    }
    os.makedirs(os.path.dirname(_AI_FILE), exist_ok=True)
    json.dump(data, open(_AI_FILE, 'w'), ensure_ascii=False, indent=2)

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
                reqs = [RequirementInfo(**r) for r in item.get('requirements', [])]
                fi = FactorInfo(
                    name=item['name'], label=item.get('label', ''),
                    category=item.get('category', ''), domain=item.get('domain', ''),
                    code=item.get('code', ''), logic_summary=item.get('logic_summary', ''),
                    data_requirements=reqs,
                )
                loaded.append({'id': item['id'], 'data': fi})
            st.session_state.ai_pending = loaded
        except Exception:
            st.session_state.ai_pending = []
    else:
        st.session_state.ai_pending = []
    st.session_state.setdefault('ai_next_id', 0)

_load_ai()

with st.expander('AI 因子生成'):
    report_text = st.text_area('研报内容', height=150, label_visibility='collapsed',
                                placeholder='粘贴研报或因子想法...')
    if st.button('生成', key='ai_generate'):
        with st.spinner('LLM 分析中...'):
            import sys as _sys
            if BASE not in _sys.path:
                _sys.path.insert(0, BASE)
            from factor_generator import generate
            _r = generate(report_text)
            if _r.error:
                st.error(_r.error)
            else:
                for _fi in _r.factors:
                    _id = st.session_state.ai_next_id
                    st.session_state.ai_next_id += 1
                    st.session_state.ai_pending.insert(0, {
                        'id': _id, 'data': _fi,
                    })
                st.session_state.ai_pending_sel = st.session_state.ai_pending[0]['id']
                _save_ai()
                if _r.usage:
                    u = _r.usage
                    st.toast(f'生成 {len(_r.factors)} 个因子，消耗 {u.get("total_tokens","-")} tokens', icon='🤖')
        st.rerun()

_pending = st.session_state.ai_pending
if _pending:
    st.markdown(f'**待处理因子 ({len(_pending)})**')
    _id2label = {p['id']: f"[{p['data'].name}] {p['data'].label}" for p in _pending}
    _sel_id = st.selectbox('选择因子', list(_id2label.keys()),
                            format_func=lambda i: _id2label[i], key='ai_pending_sel')
    _item = next(p for p in _pending if p['id'] == _sel_id)
    _fi = _item['data']

    # 查重
    _dup_name = None
    for _f in sorted(glob.glob(f'{BASE}/factors/*.py')):
        if f"@factor(name='{_fi.name}'" in open(_f).read():
            _dup_name = os.path.basename(_f)
            break
    if _dup_name:
        st.warning(f'同名因子已存在于 {_dup_name}')
    st.code(_fi.code, language='python')
    _all_ok = all(r.status == 'available' for r in _fi.data_requirements)
    for r in _fi.data_requirements:
        tag = '✅' if r.status == 'available' else '❌'
        dest = f' → {r.matched_table}.{r.matched_field}' if r.matched_table else ''
        st.markdown(f'{tag} {r.description}{dest}')
    _ai_force = False
    if _all_ok:
        _c1, _c2 = st.columns([1, 1])
        with _c1:
            _ai_force = st.checkbox('覆盖重算', key='ai_force')
        with _c2:
            if st.button('应用并运行', key='ai_run', type='primary'):
                _stdout, _stderr = _run_scratch(_fi.code, force=_ai_force)
                st.session_state.log = _stdout
                if _stderr:
                    st.session_state.log += '\n--- 错误 ---\n' + _stderr
                st.session_state.last_names = [(_fi.name, 'factor')]
                st.session_state.should_scroll = True
                st.session_state.ai_pending = [p for p in _pending if p['id'] != _sel_id]
                _save_ai()
                st.rerun()

col_left, col_right = st.columns([3, 2])

with col_left:
    st.caption('代码')
    _result = code_editor(TEMPLATE, lang='python', height='420px', key='factor_code_v1',
                          response_mode=['blur', 'debounce'],
                          options={'showInvisibles': False, 'minimap': {'enabled': False}})
    code = _result.get('text') or TEMPLATE
    c1, c2, c3 = st.columns(3)
    with c1:
        force = st.checkbox('覆盖重算')
    with c2:
        replace = st.checkbox('覆盖写入')
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
            for _name, _kind in items:
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
    st.subheader('因子函数代码')
    for _name, _kind in _last:
        _found = _get_func_code(_name, _kind)
        if _found:
            _bar = st.columns([20, 1])
            with _bar[1]:
                with st.popover('⋮'):
                    if st.button('删除', key=f'del_{_name}'):
                        _delete_factor(_name)
                        st.rerun()
            st.code(_found, language='python')

# ---- 显示结果 ----
names = st.session_state.get('last_names', [])

if names:
    st.subheader('因子评价')

    # 指标行（从 CSV，如果有）
    na = pd.isna
    for name, _kind in names:
        if _kind == 'feature':
            continue
        meta = get_factors().get(name)
        if not meta:
            continue
        if df is not None and not df.empty:
            frow = df[(df['factor'] == name) & (df['period'] == 'full')]
            if not frow.empty:
                row = frow.iloc[0]
                ic_mean_cols = sorted([c for c in row.index if c.startswith('ic_T')],
                                      key=lambda x: int(x.split('_T')[1]))
                icir_cols = sorted([c for c in row.index if c.startswith('icir_T')],
                                   key=lambda x: int(x.split('_T')[1]))

                def _small_metric(col, label, value):
                    col.markdown(f'<p style="font-size:11px;margin:0;color:#666">{label}<br>'
                                 f'<strong style="font-size:16px;color:#222">{value}</strong></p>',
                                 unsafe_allow_html=True)

                all_items = [(f'因子', name)]
                for ic, ir in zip(ic_mean_cols, icir_cols):
                    h = ic.split('_T')[1]
                    v_ic = f"{row[ic]:.4f}" if not na(row.get(ic)) else '-'
                    v_ir = f"{row[ir]:.4f}" if not na(row.get(ir)) else '-'
                    all_items.append((f'IC均值(T{h})', v_ic))
                    all_items.append((f'ICIR(T{h})', v_ir))
                if not na(row.get('long_win')):
                    all_items.append(('多头胜率', f"{row['long_win']*100:.1f}%"))
                if not na(row.get('short_win')):
                    all_items.append(('空头胜率', f"{row['short_win']*100:.1f}%"))
                if not na(row.get('long_odds')):
                    all_items.append(('多赔率', f"{row['long_odds']:.2f}"))
                if not na(row.get('short_odds')):
                    all_items.append(('空赔率', f"{row['short_odds']:.2f}"))
                if not na(row.get('kurtosis')):
                    all_items.append(('超额峰度', f"{row['kurtosis']:.2f}"))

                cols = st.columns(len(all_items))
                for i, (label, val) in enumerate(all_items):
                    _small_metric(cols[i], label, val)

    # 图表
    for name, kind in names:
        if kind == 'feature':
            continue
        meta = get_factors().get(name)
        if not meta:
            continue
        cat = meta.category
        domain = meta.domain
        func_code = _get_func_code(name, kind)
        _rebuild = [df is None or df[df['factor'] == name].empty]

        def _try_chart(load_fn, render_fn, key, *args, **kwargs):
            try:
                data = load_fn(BASE, name, cat, domain=domain) if load_fn else None
                if data is not None:
                    st.plotly_chart(render_fn(data, name, *args, **kwargs),
                                    width='stretch', key=key)
                else:
                    _rebuild[0] = True
            except Exception:
                _rebuild[0] = True

        c1, c2 = st.columns(2)
        with c1:
            _try_chart(load_ic_data, render_ic_cumulative, f'ic_{name}')
        with c2:
            _try_chart(load_ret_data, render_long_short, f'ret_{name}')

        c1, c2 = st.columns(2)
        with c1:
            _try_chart(load_ret_data, render_decile_bar, f'bar_{name}')
        with c2:
            _try_chart(load_ret_data, render_win_rate, f'win_{name}')

        try:
            ic_data = load_ic_data(BASE, name, cat, domain=domain)
            if ic_data is not None:
                hist_charts = render_ic_distribution(ic_data)
                cols = st.columns(len(hist_charts))
                for (h, fig), col in zip(hist_charts, cols):
                    with col:
                        st.plotly_chart(fig, width='stretch', key=f'hist_{name}_{h}')
            else:
                _rebuild[0] = True
        except Exception:
            _rebuild[0] = True

        if _rebuild[0] and func_code:
            st.info(f'{name} 部分分析数据缺失')
            if st.button('补全数据', key=f'rebuild_{name}'):
                with st.spinner('计算中...'):
                    stdout, stderr = _run_scratch(func_code, force=True)
                    st.session_state.log = stdout
                    if stderr:
                        st.session_state.log += '\n--- 错误 ---\n' + stderr
                    st.rerun()

    # 牛熊对比（从 CSV）
    if df is not None and not df.empty:
        _names_only = [n for n, _ in names]
        factor_df = df[df['factor'].isin(_names_only)]
        if not factor_df.empty:
            st.subheader('牛熊对比')
            ic_cols = sorted([c for c in factor_df.columns if c.startswith('ic_T')],
                             key=lambda x: int(x.split('_T')[1]))
            ir_cols = sorted([c for c in factor_df.columns if c.startswith('icir_T')],
                             key=lambda x: int(x.split('_T')[1]))
            paired = []
            for ic, ir in zip(ic_cols, ir_cols):
                paired += [ic, ir]
            extra_cols = [c for c in ['long_win', 'short_win', 'long_odds', 'short_odds'] if c in factor_df.columns]
            cols = ['factor', 'period'] + paired + extra_cols
            periods = factor_df[factor_df['period'] != 'full'][cols].copy()
            if not periods.empty:
                periods = periods.rename(columns={'period': '区间'})
                for c in ['long_win', 'short_win']:
                    if c in periods.columns:
                        periods[c] = periods[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
                for c in ['long_odds', 'short_odds']:
                    if c in periods.columns:
                        periods[c] = periods[c].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '-')
                html = periods.to_html(index=False, na_rep='-')
                html = html.replace('<table', '<table style="width:100%;table-layout:fixed;font-size:13px"')
                html = html.replace('<th>', '<th style="text-align:center">')
                html = html.replace('<td>', '<td style="text-align:center">')
                st.markdown(html, unsafe_allow_html=True)

    # scroll
    if st.session_state.pop('should_scroll', False):
        st.html("""
        <script>document.getElementById('factor-metrics').scrollIntoView({behavior:'smooth',block:'start'})</script>
        <span style="display:none">""" + str(hash(str(st.session_state.get('_sc', 0)))) + """</span>
        """, unsafe_allow_javascript=True)
        st.session_state._sc = st.session_state.get('_sc', 0) + 1
