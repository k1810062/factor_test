#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
export STREAMLIT_EMAIL=''
streamlit run src/factor_workbench/web.py
echo "按 Enter 退出..."
read
