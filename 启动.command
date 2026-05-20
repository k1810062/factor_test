#!/bin/bash
cd "$(dirname "$0")"
export PATH=$PATH:/Users/wby/Library/Python/3.9/bin
export STREAMLIT_EMAIL=''
streamlit run app.py
echo "按 Enter 退出..."
read
