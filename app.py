"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run app.py
"""

import streamlit as st
import sys, os, json, re, subprocess, tempfile, glob

sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(page_title='因子测试', layout='wide')
st.title('因子草稿测试')

TEMPLATE = '''@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
'''

# 左：代码编辑  右：日志输出
col_left, col_right = st.columns(2)

with col_left:
    force = st.checkbox('覆盖重算（勾选将重跑因子值+分析）')
    code = st.text_area('因子函数', TEMPLATE, height=400)
    run = st.button('运行')

with col_right:
    log_area = st.empty()

if run:
    with st.spinner('计算中...'):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(code)
        tmp_path = tmp.name
        tmp.close()

        cmd = ['python3', 'scratch.py']
        if force:
            cmd.append('--force')
        cmd.append(tmp_path)
        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=os.path.dirname(__file__))
        os.unlink(tmp_path)

    # 显示日志
    with col_right:
        log_area.text(result.stdout)
        if result.stderr:
            log_area.error(result.stderr)

    # 从摘要表提取结果
    csv_path = 'output/result/factor_summary.csv'
    if os.path.exists(csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)

        # 提取新因子名
        names = re.findall(r"@factor\(name='(\w+)'", code)
        factor_df = df[df['factor'].isin(names)]

        if not factor_df.empty:
            st.subheader('因子评价')
            # 显示关键指标（取第一个因子的全量 period）
            full = factor_df[factor_df['period'] == 'full']
            if not full.empty:
                row = full.iloc[0]
                na = pd.isna
                cols = st.columns(5)
                cols[0].metric('IC 均值(T1)', f"{row['ic_mean_T1']:.4f}" if not na(row.get('ic_mean_T1')) else '-')
                cols[1].metric('ICIR(T1)', f"{row['icir_T1']:.4f}" if not na(row.get('icir_T1')) else '-')
                cols[2].metric('多头胜率', f"{row['long_win']:.1%}" if not na(row.get('long_win')) else '-')
                cols[3].metric('空头胜率', f"{row['short_win']:.1%}" if not na(row.get('short_win')) else '-')
                cols[4].metric('超额峰度', f"{row['kurtosis']:.2f}" if not na(row.get('kurtosis')) else '-')

            # 显示分析图
            for name in names:
                for cat in ('pv', 'fund', 'ind', 'monthly'):
                    ic_png = f'output/factor_analysis/{cat}/{name}/ic/ic_cum.png'
                    if os.path.exists(ic_png):
                        st.image(ic_png, caption=f'{name} 累计 IC', use_container_width=True)
                        break
                for cat in ('pv', 'fund', 'ind', 'monthly'):
                    ret_png = f'output/factor_analysis/{cat}/{name}/ret/ret_long_short.png'
                    if os.path.exists(ret_png):
                        st.image(ret_png, caption=f'{name} 多空收益', use_container_width=True)
                        break

            # 牛熊对比表
            st.subheader('牛熊对比')
            periods = factor_df[factor_df['period'] != 'full'][['period', 'ic_mean_T1', 'icir_T1', 'long_win', 'short_win']]
            if not periods.empty:
                periods = periods.rename(columns={
                    'period': '区间', 'ic_mean_T1': 'IC均值', 'icir_T1': 'ICIR',
                    'long_win': '多头胜率', 'short_win': '空头胜率',
                })
                for c in ['多头胜率', '空头胜率']:
                    if c in periods.columns:
                        periods[c] = periods[c].apply(lambda x: f'{x:.1%}' if pd.notna(x) else '-')
                st.dataframe(periods, hide_index=True)
