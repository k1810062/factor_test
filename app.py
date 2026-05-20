"""Web 界面：写因子 → 点按钮 → 跑 scratch → 看结果。

启动：streamlit run app.py
"""

import streamlit as st
import sys, os, json, re, subprocess, tempfile

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

code = st.text_area('因子函数', TEMPLATE, height=300)

if st.button('运行'):
    with st.spinner('计算中...'):
        # 写临时文件
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(code)
        tmp_path = tmp.name
        tmp.close()

        # 跑 scratch
        result = subprocess.run(
            ['python3', 'scratch.py', tmp_path],
            capture_output=True, text=True, cwd=os.path.dirname(__file__)
        )
        os.unlink(tmp_path)

    st.text(result.stdout)
    if result.stderr:
        st.error(result.stderr)

    # 显示汇总表
    csv_path = 'output/result/factor_summary.csv'
    if os.path.exists(csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)
        st.subheader('汇总表')
        st.dataframe(df)
