"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run app.py
"""

import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)

st.set_page_config(page_title='因子测试', layout='wide')
st.title('因子草稿测试')

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
            cols = st.columns(5)
            cols[0].metric('IC 均值(T1)', f"{row['ic_mean_T1']:.4f}" if not na(row.get('ic_mean_T1')) else '-')
            cols[1].metric('ICIR(T1)', f"{row['icir_T1']:.4f}" if not na(row.get('icir_T1')) else '-')
            cols[2].metric('多头胜率', f"{row['long_win']:.1f}%" if not na(row.get('long_win')) else '-')
            cols[3].metric('空头胜率', f"{row['short_win']:.1f}%" if not na(row.get('short_win')) else '-')
            cols[4].metric('超额峰度', f"{row['kurtosis']:.2f}" if not na(row.get('kurtosis')) else '-')

        cat_map = dict(zip(factor_df['factor'], factor_df['cat']))
        for name in names:
            cat = cat_map.get(name)
            if not cat:
                continue
            ic_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ic/ic_cum.png')
            if os.path.exists(ic_png):
                st.image(ic_png, caption=f'{name} 累计 IC', use_container_width=True)
            ret_png = os.path.join(BASE, f'output/factor_analysis/{cat}/{name}/ret/ret_long_short.png')
            if os.path.exists(ret_png):
                st.image(ret_png, caption=f'{name} 多空收益', use_container_width=True)

        st.subheader('牛熊对比')
        periods = factor_df[factor_df['period'] != 'full'][['period', 'ic_mean_T1', 'icir_T1', 'long_win', 'short_win']].copy()
        if not periods.empty:
            periods = periods.rename(columns={
                'period': '区间', 'ic_mean_T1': 'IC均值', 'icir_T1': 'ICIR',
                'long_win': '多头胜率', 'short_win': '空头胜率',
            })
            for c in ['多头胜率', '空头胜率']:
                if c in periods.columns:
                    periods[c] = periods[c].apply(lambda x: f'{x:.1f}%' if pd.notna(x) else '-')
            st.dataframe(periods, hide_index=True)
