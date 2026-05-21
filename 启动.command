#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
export STREAMLIT_EMAIL=''
streamlit run app.py
echo "按 Enter 退出..."
read
