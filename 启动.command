#!/bin/bash
cd "$(dirname "$0")"
.venv/bin/streamlit run src/factor_workbench/web.py
echo "按 Enter 退出..."
read
