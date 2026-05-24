# 因子研究工作台

A 股行业/个股因子计算、分析、可视化的工具包。

## 快速开始

```bash
pip install -e .
streamlit run src/factor_workbench/web.py
```

## 结构

```
src/factor_workbench/       ← 工具包
├── web.py                  ← Web 界面入口（streamlit run）
├── run.py                  ← 全量跑 pipeline
├── scratch.py              ← 写新因子→注册→跑
├── registry.py             ← @factor/@feature 装饰器
├── pipeline.py             ← 调度引擎
├── data_api.py             ← 数据访问层（DuckDB/Parquet）
├── metric_runner.py        ← 评价指标调度
├── ic_metric.py            ← IC 分析（年化 + Newey-West）
├── rr_metric.py / sig_metric.py / chart_metric.py
├── chart_renderer.py       ← 浏览器交互图
├── summarize_results.py    ← 汇总 CSV
└── auto_config.py          ← 自动发现 parquet → 配置

factors/                     ← 因子函数
├── industry_factors.py       (26 个行业因子)
└── industry_monthly_factors.py (5 个月度因子)

features/                    ← 特征函数（中间量，只计算不分析）
└── stock_features.py         (9 个股票特征)
```

## 使用方式

**浏览器写因子测试：**
```
streamlit run src/factor_workbench/web.py
```
在代码框里写 `@factor` 函数 → 点运行 → 自动注册 → 出图

**全量跑：**
```
python3 -m factor_workbench.run
```

**终端测新因子：**
```
python3 -m factor_workbench.scratch my_factor.py
```

## 关键概念

- `@factor` — 因子，计算+分析
- `@feature` — 特征/中间量，只计算不分析
- domain 含频率：`industry`（日频）、`industry_monthly`（月频）
- 配置自动生成，无需手动编辑
- 装饰器用 ast 解析，不依赖参数格式

## 启动.command

macOS 用户双击该文件即可启动网页。
