#!/bin/bash
cd "$(dirname "$0")"
export FACTOR_DATA="${FACTOR_DATA:-"$(dirname "$PWD")/factor_data"}"
echo "FACTOR_DATA=$FACTOR_DATA"

if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv
    .venv/bin/pip install -e .
fi

.venv/bin/streamlit run src/factor_workbench/web.py
echo "按 Enter 退出..."
read
