# 行业因子分析系统

A 股行业板块因子计算、IC/RR/SIG 分析的全流程框架。

## 快速开始

```bash
cd factor_system
python3 main.py          # 全量增量运行（已有因子跳过）
```

## 架构

```
main.py                          入口
  └── framework/pipeline.py      调度（因子计算 → 分析 → 汇总）
        ├── framework/data_api.py    数据访问层
        ├── framework/registry.py    @factor / @metric 装饰器
        └── framework/metric_runner.py   评价指标循环 + 子区间
              ├── metrics/ic_metric.py       Rank IC（DuckDB SQL 加速）
              ├── metrics/rr_metric.py       胜率 + 尾部赔率
              ├── metrics/sig_metric.py      峰度 + ACF(1)
              └── metrics/chart_metric.py    统计图
```

## 配置文件

`config/config.json` 控制哪些因子运行、跑哪些分析：

```json
{
  "stock": { "因子名": {"cat": "分类", "label": "中文名"}, ... },
  "industry": { ... },
  "monthly": { ... },
  "analysis": ["charts", "ic", "rr", "sig"],
  "sub_period": {
    "from_file": "data/market_periods.json",
    "groups": ["bull", "bear", "consolidate"]
  }
}
```

### 分析覆盖模式

```json
"analysis_overwrite": ["charts", "ic"]   # 全局：删除所有因子的 charts/ic 分析目录
"up_ratio": {"cat":"pv", "label":"上涨家数占比", "overwrite": ["ic"]}   # 单因子覆盖
```

## 验证一个因子

这是系统的核心功能。有两种方式：

### 方式一：草稿模式（推荐）

在 `factors/scratch/` 下新建一个文件，写因子函数：

```python
# factors/scratch/ret_5d.py
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
```

然后运行：

```bash
python3 scratch.py factors/scratch/ret_5d.py
```

自动完成：
1. 因子函数追加到 `factors/industry_factors.py`
2. `config/config.json` 改写为只跑这个因子
3. 跑 `main.py`（因子计算 → 4 项分析 → 汇总表）

跑完后 `config/config.json` 里只有这个因子。要跑全量时改回来就行。

### 方式二：直接添加

```python
# 1. factors/industry_factors.py 写函数
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    ...

# 2. config/config.json 添加一行
"ret_5d": {"cat": "pv", "label": "5日涨幅"}

# 3. 运行
python3 main.py
```

### 验证结果怎么看

| 指标 | 文件 | 说明 |
|------|------|------|
| IC | `output/factor_analysis/{cat}/{name}/ic/{name}_ic.txt` | IC 均值、ICIR、t 统计量 |
| 十分组收益 | `output/factor_analysis/{cat}/{name}/ret/{name}_ret.txt` | 多头(D10)/空头(D1)/多空收益 |
| 胜率 | `output/factor_analysis/{cat}/{name}/rr/{name}_rr.txt` | 多头/空头胜率、尾部赔率 |
| 峰度/ACF | `output/factor_analysis/{cat}/{name}/sig/{name}_sig.txt` | 超额峰度、ACF(1) 行业截面统计 |
| 汇总表 | `output/result/factor_summary.csv` | 所有因子 × 牛熊全周期汇总 |

## 因子函数写法

支持两种方式：

### SQL 版（DuckDB 加速）

```python
@factor(name='mom_12m', category='ind', label='动量因子', domain='industry')
def mom_12m(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (LAG(CLOSE, 21) OVER w / LAG(CLOSE, 252) OVER w - 1) as mom_12m
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
```

### pandas 版

```python
@factor(name='ma5_ratio', category='pv', label='MA5上方占比', domain='industry')
def ma5_ratio(api):
    stock = api.table('stock_base', columns=['STOCK_CODE', 'TRADE_DATE', 'CLOSE'])
    mapping = api.table('factor_stock', columns=['STOCK_CODE', 'TRADE_DATE', 'industry_code'])
    stock = stock.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    stock = stock.sort_values(['STOCK_CODE', 'TRADE_DATE'])
    ma5 = stock.groupby('STOCK_CODE')['CLOSE'].transform(lambda x: x.rolling(5).mean())
    stock['above_ma5'] = (stock['CLOSE'] > ma5).astype(int)
    return stock.groupby(['industry_code', 'TRADE_DATE'])['above_ma5'].mean().reset_index(name='ma5_ratio')
```

## 数据源

通过 `api.table()` 访问，不写文件路径。目前支持的表：

| 表名 | 文件 | 内容 |
|------|------|------|
| `stock_base` | `data/stock_base.parquet` | 个股日线（CLOSE, VOL, AMOUNT, MV, TURN, ROE_TTM, BORROW_BUY/REPAY 等） |
| `swi_daily` | `data/SWI_daily.parquet` | 申万行业指数日线（STOCK_CODE=行业代码, CLOSE） |
| `etf_daily` | `data/etf_daily.parquet` | 行业 ETF 资金流 |
| `factor_stock` | `output/data_processed/factor_stock.parquet` | 个股因子 |
| `industry_daily` | `output/data_processed/industry_daily_ratio.parquet` | 行业因子 |
| `industry_monthly` | `output/data_processed/industry_monthly_ratio.parquet` | 月度因子 |

## 子区间分析

预定义牛熊震荡区间（`data/market_periods.json`）：

| 周期 | 阶段 |
|------|------|
| bull | 199905-200106, 200506-200710, 200810-200908, 201407-201506, 201901-202102, 202409-至今 |
| bear | 200106-200506, 200710-200810, 200908-201407, 201506-201601, 202102-202409 |
| consolidate | 201601-201901 |

每个因子在每个区间都会跑完整分析，输出到 `output/factor_analysis_{suffix}/`。

## 输出结构

```
output/
├── data_processed/
│   ├── factor_stock.parquet           个股因子表
│   ├── industry_daily_ratio.parquet   行业因子日度
│   ├── industry_daily_ratio_z.parquet Z-score 标准化
│   └── industry_monthly_ratio.parquet 月度因子
├── factor_analysis/                   全量分析
├── factor_analysis_bull/              牛市子区间
├── factor_analysis_bear/              熊市子区间
└── result/factor_summary.csv          汇总表
```

## 依赖

Python 3.9+, pandas, numpy, scipy, matplotlib, duckdb
