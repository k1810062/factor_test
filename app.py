"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run app.py
"""

import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)

st.set_page_config(page_title='因子测试', layout='wide')
st.title('因子测试')


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

col_left, col_right = st.columns(2)

with col_left:
    code = st.text_area('因子函数', TEMPLATE, height=420, label_visibility='collapsed')
    c1, c2 = st.columns(2)
    with c1:
        force = st.checkbox('覆盖重算')
    with c2:
        run = st.button('运行', use_container_width=True)

with col_right:
    log_text = st.session_state.get('log', '')
    st.text_area('运行日志', log_text, height=420, label_visibility='collapsed', disabled=True)

# ---- 运行流程 ----
if run:
    # 第1步：清空旧内容，立即重绘
    st.session_state.log = ''
    st.session_state.last_names = []
    st.session_state.pending = True
    st.rerun()

if st.session_state.get('pending'):
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

# ---- 显示结果 ----
names = st.session_state.get('last_names', [])

if names and os.path.exists(csv_path):
    import pandas as pd
    df = pd.read_csv(csv_path)
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

            st.divider()

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
                    st.plotly_chart(fig, use_container_width=True, key=f'ic_{name}')
                else:
                    ic_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ic/ic_cum.png')
                    if os.path.exists(ic_png):
                        st.image(ic_png, caption=f'{name} 累计 IC', use_container_width=True)
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
                    st.plotly_chart(fig2, use_container_width=True, key=f'ret_{name}')
                else:
                    ret_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ret/ret_long_short.png')
                    if os.path.exists(ret_png):
                        st.image(ret_png, caption=f'{name} 多空收益', use_container_width=True)

            # 十分组日均收益柱状图
            if os.path.exists(ret_parquet):
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
                st.plotly_chart(fig3, use_container_width=True, key=f'bar_{name}')

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
