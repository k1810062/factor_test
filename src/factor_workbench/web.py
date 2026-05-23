"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run src/factor_workbench/web.py
"""

import ast, time
import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob, numpy as np
from code_editor import code_editor

from factor_workbench.chart_renderer import (
    load_ic_data, load_ret_data, data_exists,
    render_ic_cumulative, render_long_short,
    render_decile_bar, render_win_rate, render_ic_distribution,
)
from factor_workbench.registry import get_factors, load_factor_modules
from factor_workbench.auto_config import generate_config

BASE = os.getcwd()
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

TEMPLATE = '''@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / lag(close, 5) OVER w - 1) as ret_5d
        FROM industry_price
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


def _get_factor_code(name):
    """从文件提取 @factor/@feature 函数代码。"""
    import glob
    for f in sorted(glob.glob(f'{BASE}/factors/*.py') + glob.glob(f'{BASE}/features/*.py')):
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


def _replace_factor(name, code):
    """替换文件中的同名函数。按类型优先搜索对应文件。"""
    kind = 'feature' if f"@feature(name='{name}'" in code else 'factor'
    func_code = _extract_func(code, name, kind)
    if not func_code:
        return
    # 特征优先 features.py，因子优先 industry/monthly
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
    cmd = [sys.executable, '-m', 'factor_workbench.scratch']
    if force:
        cmd.append('--force')
    cmd.append(tmp_path)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    os.unlink(tmp_path)
    return result.stdout, result.stderr


# ---- 因子搜索 ----
import pandas as pd

# 读 CSV（如果有）
df = None
full_period = pd.DataFrame()
if os.path.exists(csv_path):
    df = pd.read_csv(csv_path)
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
disp_cols = ['factor', 'label', 'cat', 'ic_T1', 'icir_T1', 'long_win', 'kurtosis']
disp_cols = [c for c in disp_cols if c in all_factors.columns]

c1, c2 = st.columns([4, 1])
with c1:
    with st.form(key='search_form', border=False):
        cols = st.columns([3, 1])
        with cols[0]:
            q = st.text_input('🔍 搜索因子', placeholder='输入因子名、中文名或分类...',
                             label_visibility='collapsed', key='search_input')
        with cols[1]:
            submitted = st.form_submit_button('搜索', width='stretch')
            if submitted:
                st.session_state.mode = 'search'
with c2:
    if st.button('因子列表', width='stretch'):
        st.session_state.mode = 'list'

mode = st.session_state.get('mode', '')
q_lower = q.lower() if q else ''

# ---- 搜索模式 ----
if mode == 'search' and q_lower:
    matched = all_factors[
        all_factors['factor'].str.lower().str.contains(q_lower, na=False) |
        all_factors['label'].str.lower().str.contains(q_lower, na=False) |
        all_factors['cat'].str.lower().str.contains(q_lower, na=False)
    ]
    if not matched.empty:
        st.caption(f'搜索列表  共 {matched["factor"].nunique()} 个因子')
        show = matched[disp_cols].copy()
        show.columns = ['因子名', '标签', '分类', 'IC均值', 'ICIR', '多头胜率', '峰度']
        for c in ['多头胜率']:
            if c in show.columns:
                show[c] = show[c].apply(lambda x: f'{x:.1f}%' if pd.notna(x) else '-')
        event = st.dataframe(show, hide_index=True, width='stretch',
                             column_config={c: st.column_config.TextColumn(c, alignment='center') for c in show.columns},
                             on_select='rerun', selection_mode='single-row',
                             key=f'search_tbl_{st.session_state.get("search_key", "")}')
        if event and event.selection and event.selection.rows:
            idx = event.selection.rows[0]
            selected_name = matched.iloc[idx]['factor']
            st.session_state.last_names = [selected_name]
            st.session_state.should_scroll = True
    else:
        st.caption(f'未找到含 "{q}" 的因子')

# ---- 列表模式 ----
if mode == 'list':
    all_show = all_factors[disp_cols].copy()
    all_show = all_show.sort_values('factor')
    all_show.columns = ['因子名', '标签', '分类', 'IC均值', 'ICIR', '多头胜率', '峰度']
    for c in ['多头胜率']:
        if c in all_show.columns:
            all_show[c] = all_show[c].apply(lambda x: f'{x:.1f}%' if pd.notna(x) else '-')
    st.caption(f'因子列表  共 {all_show["因子名"].nunique()} 个因子')
    ev = st.dataframe(all_show, hide_index=True, width='stretch', height=400,
                     column_config={c: st.column_config.TextColumn(c, alignment='center') for c in all_show.columns},
                     on_select='rerun', selection_mode='single-row',
                     key=f'all_tbl_{st.session_state.get("search_key", "")}')
    if ev and ev.selection and ev.selection.rows:
        idx = ev.selection.rows[0]
        _all_names = all_show['因子名'].tolist()
        if idx < len(_all_names):
            st.session_state.last_names = [_all_names[idx]]
            st.session_state.should_scroll = True

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
        cmd = [sys.executable, '-m', 'factor_workbench.scratch']
        if force or replace:
            cmd.append('--force')
        cmd.append(tmp_path)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
        os.unlink(tmp_path)

        # pipeline 跑成功后才执行代码替换
        if result.returncode == 0 and st.session_state.pop('replace_pending', False):
            names_in_code = re.findall(r"@(?:factor|feature)\(name='(\w+)'", code)
            for _name in names_in_code:
                _replace_factor(_name, code)

    st.session_state.pending = False
    st.session_state.log = result.stdout
    if result.stderr:
        st.session_state.log += '\n--- 错误 ---\n' + result.stderr
    st.session_state.last_names = re.findall(r"@(?:factor|feature)\(name='(\w+)'", code)
    st.session_state.should_scroll = True
    st.rerun()

st.markdown('<div id="factor-metrics"></div>', unsafe_allow_html=True)

# ---- 展示选中因子的函数代码 ----
_last = st.session_state.get('last_names', [])
if _last:
    st.subheader('因子函数代码')
    for _name in _last:
        _found = _get_factor_code(_name)
        if _found:
            st.code(_found, language='python')

# ---- 显示结果 ----
names = st.session_state.get('last_names', [])

if names:
    st.subheader('因子评价')

    # 指标行（从 CSV，如果有）
    na = pd.isna
    for name in names:
        meta = get_factors().get(name)
        if not meta:
            continue
        if df is not None and os.path.exists(csv_path):
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
                    all_items.append(('多头胜率', f"{row['long_win']:.1f}%"))
                if not na(row.get('short_win')):
                    all_items.append(('空头胜率', f"{row['short_win']:.1f}%"))
                if not na(row.get('long_odds')):
                    all_items.append(('多赔率', f"{row['long_odds']:.2f}"))
                if not na(row.get('short_odds')):
                    all_items.append(('空赔率', f"{row['short_odds']:.2f}"))
                if not na(row.get('kurtosis')):
                    all_items.append(('超额峰度', f"{row['kurtosis']:.2f}"))

                cols = st.columns(len(all_items))
                for i, (label, val) in enumerate(all_items):
                    _small_metric(cols[i], label, val)

    # 图表（从 parquet，不受 CSV 影响）
    for name in names:
        meta = get_factors().get(name)
        if not meta:
            continue
        cat = meta.category

        if not data_exists(BASE, name, cat):
            st.info(f'{name} 分析数据缺失')
            factor_code = _get_factor_code(name)
            if factor_code and st.button('补全数据', key=f'rebuild_{name}'):
                with st.spinner('计算中...'):
                    stdout, stderr = _run_scratch(factor_code, force=True)
                    st.session_state.log = stdout
                    if stderr:
                        st.session_state.log += '\n--- 错误 ---\n' + stderr
                    st.rerun()
            continue

        ic_df = load_ic_data(BASE, name, cat)
        ret_df = load_ret_data(BASE, name, cat)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(render_ic_cumulative(ic_df, name),
                            width='stretch', key=f'ic_{name}')
        with c2:
            st.plotly_chart(render_long_short(ret_df, name),
                            width='stretch', key=f'ret_{name}')

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(render_decile_bar(ret_df, name),
                            width='stretch', key=f'bar_{name}')
        with c2:
            st.plotly_chart(render_win_rate(ret_df, name),
                            width='stretch', key=f'win_{name}')

        hist_charts = render_ic_distribution(ic_df)
        cols = st.columns(len(hist_charts))
        for (h, fig), col in zip(hist_charts, cols):
            with col:
                st.plotly_chart(fig, width='stretch', key=f'hist_{name}_{h}')

    # 牛熊对比（从 CSV）
    if df is not None and os.path.exists(csv_path):
        factor_df = df[df['factor'].isin(names)]
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
                        periods[c] = periods[c].apply(lambda x: f'{x:.1f}%' if pd.notna(x) else '-')
                for c in ['long_odds', 'short_odds']:
                    if c in periods.columns:
                        periods[c] = periods[c].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '-')
                html = periods.to_html(index=False, na_rep='-')
                html = html.replace('<table', '<table style="width:100%;table-layout:fixed;font-size:13px"')
                html = html.replace('<th>', '<th style="text-align:center">')
                html = html.replace('<td>', '<td style="text-align:center">')
                st.markdown(html, unsafe_allow_html=True)

    # scroll（不受 CSV 影响）
    if st.session_state.pop('should_scroll', False):
        st.html("""
        <script>document.getElementById('factor-metrics').scrollIntoView({behavior:'smooth',block:'start'})</script>
        <span style="display:none">""" + str(hash(str(st.session_state.get('_sc', 0)))) + """</span>
        """, unsafe_allow_javascript=True)
        st.session_state._sc = st.session_state.get('_sc', 0) + 1
