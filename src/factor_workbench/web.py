"""Web 入口：st.navigation 切换个股/行业页面。

启动：streamlit run src/factor_workbench/web.py
"""
import streamlit as st

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

from factor_workbench.web_shared import *
from factor_workbench.stock_page import stock_page as _stock_raw
from factor_workbench.industry_page import industry_page as _industry_raw
import traceback

def _wrap(fn, name):
    def wrapped():
        try:
            fn()
        except Exception:
            with open('/tmp/page_errors.log', 'a') as f:
                f.write(f'--- {name} ---\n{traceback.format_exc()}\n')
            raise
    wrapped.__name__ = name + '_page'
    return wrapped

stock_page = _wrap(_stock_raw, 'stock')
industry_page = _wrap(_industry_raw, 'industry')

st.navigation([
    st.Page(stock_page, title="个股", icon="📈"),
    st.Page(industry_page, title="行业", icon="🏭"),
]).run()

