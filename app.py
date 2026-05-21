"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run app.py
"""

import ast, time
import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob, numpy as np
from code_editor import code_editor

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)

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
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
'''

# ---- 因子搜索 ----
if os.path.exists(csv_path):
    import pandas as pd
    df = pd.read_csv(csv_path)
    full_period = df[df['period'] == 'full'].copy()

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
        matched = full_period[
            full_period['factor'].str.lower().str.contains(q_lower, na=False) |
            full_period['label'].str.lower().str.contains(q_lower, na=False) |
            full_period['cat'].str.lower().str.contains(q_lower, na=False)
        ]
        if not matched.empty:
            st.caption(f'搜索列表  共 {matched["factor"].nunique()} 个因子')
            show = matched[['factor', 'label', 'cat', 'ic_mean_T1', 'icir_T1', 'long_win', 'kurtosis']].copy()
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
        all_show = full_period[['factor', 'label', 'cat', 'ic_mean_T1', 'icir_T1', 'long_win', 'kurtosis']].copy()
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
    _result = code_editor(TEMPLATE, lang='python', height='420px', key='factor_code',
                          response_mode=['blur', 'debounce'],
                          options={'showInvisibles': False, 'minimap': {'enabled': False}})
    code = _result.get('text') or TEMPLATE
    c1, c2 = st.columns(2)
    with c1:
        force = st.checkbox('覆盖重算')
    with c2:
        run = st.button('运行', width='stretch')

with col_right:
    st.caption('运行日志')
    log_text = st.session_state.get('log', '')
    st.text_area('运行日志', log_text, height=420, label_visibility='collapsed', disabled=True)

# ---- 运行流程 ----
if run:
    # 第1步：清空旧内容，立即重绘
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
        cmd = ['python3', 'scratch.py']
        if force:
            cmd.append('--force')
        cmd.append(tmp_path)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
        os.unlink(tmp_path)
    st.session_state.pending = False
    st.session_state.log = result.stdout
    if result.stderr:
        st.session_state.log += '\n--- 错误 ---\n' + result.stderr
    st.session_state.last_names = re.findall(r"@factor\(name='(\w+)'", code)
    st.rerun()

st.markdown('<div id="factor-metrics"></div>', unsafe_allow_html=True)

# ---- 展示选中因子的函数代码 ----
_last = st.session_state.get('last_names', [])
if _last and os.path.exists(csv_path):
    _name = _last[0]
    _found = None
    for _f in ['factors/industry_factors.py', 'factors/stock_factors.py', 'factors/monthly_factors.py']:
        _fp = os.path.join(BASE, _f)
        if os.path.exists(_fp):
            _txt = open(_fp).read()
            _i = _txt.find(f"@factor(name='{_name}'")
            if _i >= 0:
                _e = _txt.find('\n@factor(', _i + 1)
                if _e < 0:
                    _e = len(_txt)
                _found = _txt[_i:_e].strip()
                break
    if _found:
        st.subheader('因子函数代码')
        st.code(_found, language='python')

# ---- 显示结果 ----
names = st.session_state.get('last_names', [])

if names and os.path.exists(csv_path):
    factor_df = df[df['factor'].isin(names)]
    na = pd.isna

    if not factor_df.empty:
        st.subheader('因子评价')

        full = factor_df[factor_df['period'] == 'full']
        if not full.empty:
            row = full.iloc[0]
            # 动态读取 CSV 中的 IC 均值和 ICIR 列
            ic_mean_cols = sorted([c for c in row.index if c.startswith('ic_mean_T')],
                                  key=lambda x: int(x.split('_T')[1]))
            icir_cols = sorted([c for c in row.index if c.startswith('icir_T')],
                               key=lambda x: int(x.split('_T')[1]))

            def _small_metric(col, label, value):
                col.markdown(f'<p style="font-size:12px;margin:0;color:#666">{label}<br>'
                             f'<strong style="font-size:18px;color:#222">{value}</strong></p>',
                             unsafe_allow_html=True)

            # 收集所有指标到一行（IC 和 IR 成对）
            all_items = []
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

        import plotly.graph_objects as go
        cat_map = dict(zip(factor_df['factor'], factor_df['cat']))
        for name in names:
            cat = cat_map.get(name)
            if not cat:
                continue

            c1, c2 = st.columns(2)
            with c1:
                ic_parquet = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ic/{name}_ic.parquet')
                if os.path.exists(ic_parquet):
                    ic_df = pd.read_parquet(ic_parquet)
                    ic_df['TRADE_DATE'] = pd.to_datetime(ic_df['TRADE_DATE'], format='%Y%m%d')
                    ic_df = ic_df.sort_values('TRADE_DATE').reset_index(drop=True)
                    fig = go.Figure()
                    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
                    for h, color in zip([c for c in ic_df.columns if c != 'TRADE_DATE'], colors):
                        vals = ic_df[h].dropna().cumsum()
                        fig.add_trace(go.Scatter(x=vals.index, y=vals.values, mode='lines',
                            name=h, line=dict(color=color, width=1.5)))
                    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
                    fig.update_layout(title=f'{name} 累计 Rank IC',
                        hovermode='x unified', height=300,
                        margin=dict(l=10, r=10, t=30, b=10), showlegend=True)
                    st.plotly_chart(fig, width='stretch', key=f'ic_{name}')
                else:
                    ic_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ic/ic_cum.png')
                    if os.path.exists(ic_png):
                        st.image(ic_png, caption=f'{name} 累计 IC', width='stretch')
            with c2:
                ret_parquet = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ret/{name}_decile_rets.parquet')
                if os.path.exists(ret_parquet):
                    ret_df = pd.read_parquet(ret_parquet)
                    cum = (1 + ret_df).cumprod() - 1
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(x=cum.index, y=cum[9], mode='lines',
                        name='多头(D10)', line=dict(color='crimson', width=1.5)))
                    fig2.add_trace(go.Scatter(x=cum.index, y=cum[0], mode='lines',
                        name='空头(D1)', line=dict(color='steelblue', width=1.5)))
                    fig2.add_trace(go.Scatter(x=cum.index, y=cum[9] - cum[0], mode='lines',
                        name='多空(D10-D1)', line=dict(color='darkgreen', width=2)))
                    fig2.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
                    fig2.update_layout(title=f'{name} 多空收益',
                        hovermode='x unified', height=300,
                        margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig2, width='stretch', key=f'ret_{name}')
                else:
                    ret_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ret/ret_long_short.png')
                    if os.path.exists(ret_png):
                        st.image(ret_png, caption=f'{name} 多空收益', width='stretch')

            # 十分组收益柱状图 + 胜率柱状图（并排）
            if os.path.exists(ret_parquet):
                c1, c2 = st.columns(2)
                with c1:
                    means = ret_df.mean() * 100
                    bar_colors = ['#1a9850','#91cf60','#d9ef8b','#fee08b','#fc8d59',
                                  '#ef6548','#d73027','#b30000','#7f0000','#4d0000']
                    fig3 = go.Figure()
                    fig3.add_trace(go.Bar(x=[f'D{i+1}' for i in range(10)], y=means.values,
                        marker_color=bar_colors))
                    fig3.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
                    fig3.update_layout(title=f'{name} 十分组日均收益',
                        xaxis_title='分组', yaxis_title='日均收益率(%)',
                        height=300, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig3, width='stretch', key=f'bar_{name}')
                with c2:
                    win_rates = (ret_df > 0).mean() * 100
                    fig5 = go.Figure()
                    fig5.add_trace(go.Bar(x=[f'D{i+1}' for i in range(10)], y=win_rates.values,
                        marker_color=bar_colors))
                    fig5.add_hline(y=50, line_dash='dash', line_color='gray', line_width=0.6)
                    fig5.update_layout(title=f'{name} 十分组胜率',
                        xaxis_title='分组', yaxis_title='胜率(%)', yaxis=dict(range=[0, 100]),
                        height=300, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig5, width='stretch', key=f'win_{name}')

            # IC 分布直方图（一行4个）
            ic_parquet = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ic/{name}_ic.parquet')
            if os.path.exists(ic_parquet):
                ic_df = pd.read_parquet(ic_parquet)
                horizons = [c for c in ic_df.columns if c != 'TRADE_DATE']
                cols = st.columns(len(horizons))
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
                for idx, h in enumerate(horizons):
                    with cols[idx]:
                        vals = ic_df[h].dropna()
                        mu, sigma = vals.mean(), vals.std()
                        x_range = np.linspace(vals.min(), vals.max(), 100)
                        fig4 = go.Figure()
                        fig4.add_trace(go.Histogram(x=vals, histnorm='probability density',
                            nbinsx=40, name=f'T+{h}', marker_color=colors[idx], opacity=0.7))
                        fig4.add_trace(go.Scatter(x=x_range, y=np.exp(-(x_range-mu)**2/(2*sigma**2))/(sigma*np.sqrt(2*np.pi)),
                            mode='lines', name='正态分布', line=dict(color='red', width=1.5)))
                        fig4.add_vline(x=mu, line_dash='dash', line_color='crimson', line_width=1.2)
                        fig4.update_layout(title=f'T+{h} IC 分布', height=250,
                            margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
                        st.plotly_chart(fig4, width='stretch', key=f'hist_{name}_{h}')

        st.subheader('牛熊对比')
        ic_cols = sorted([c for c in factor_df.columns if c.startswith('ic_mean_T')],
                         key=lambda x: int(x.split('_T')[1]))
        ir_cols = sorted([c for c in factor_df.columns if c.startswith('icir_T')],
                         key=lambda x: int(x.split('_T')[1]))
        # IC 和 IR 按周期配对排列
        paired = []
        for ic, ir in zip(ic_cols, ir_cols):
            paired += [ic, ir]
        extra_cols = [c for c in ['long_win', 'short_win', 'long_odds', 'short_odds'] if c in factor_df.columns]
        cols = ['period'] + paired + extra_cols
        periods = factor_df[factor_df['period'] != 'full'][cols].copy()
        if not periods.empty:
            periods = periods.rename(columns={'period': '区间'})
            for c in ['long_win', 'short_win']:
                if c in periods.columns:
                    periods[c] = periods[c].apply(lambda x: f'{x:.1f}%' if pd.notna(x) else '-')
            for c in ['long_odds', 'short_odds']:
                if c in periods.columns:
                    periods[c] = periods[c].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '-')
            # 用 HTML 表格居中显示，等宽
            html = periods.to_html(index=False, na_rep='-')
            html = html.replace('<table', '<table style="width:100%;table-layout:fixed;font-size:13px"')
            html = html.replace('<th>', '<th style="text-align:center">')
            html = html.replace('<td>', '<td style="text-align:center">')
            st.markdown(html, unsafe_allow_html=True)

            if st.session_state.pop('should_scroll', False):
                st.html("""
                <script>document.getElementById('factor-metrics').scrollIntoView({behavior:'smooth',block:'start'})</script>
                """, unsafe_allow_javascript=True)
