# 行业因子分析系统

A 股行业板块因子计算、截面标准化、IC/RR/SIG 分析的全流程框架。

## 架构

```
stock_base.parquet         个股基础数据
    ↓
stock_factor_builder.py    个股因子计算
    ↓
factor_stock.parquet       个股因子表
    ↓
run_pipeline.py            行业因子 → Z-score → 分析
    ├── compute_industry_factors()   行业因子聚合 + 增量追加
    ├── compute_zscore()             截面 Z-score 标准化
    ├── compute_monthly_factors()    月度因子计算
    ├── run_analysis()               运行分析脚本
    │    ├── analyze_factors.py       统计图（分布/时序/行业柱状）
    │    ├── analyze_factor_ic.py     Rank IC + 十分组收益
    │    ├── analyze_factor_rr.py     胜率 + 尾部赔率
    │    ├── analyze_factor_sig.py    峰度 + ACF(1)
    │    └── analyze_factor_monthly.py 月度因子分析
    └── summarize_results.py         汇总 → result/factor_summary.csv
```

## 数据依赖

| 文件 | 内容 | 大小 |
|------|------|------|
| `data/stock_base.parquet` | 个股日线基础数据（行情、财务、资金） | ~295MB |
| `data/SWI_daily.parquet` | 申万行业指数日线 | ~473KB |
| `data/etf_daily.parquet` | 行业 ETF 资金流向 | ~2.4MB |
| `data/market_periods.json` | 牛熊震荡区间定义 | |

**个股数据字段要求**（`stock_base.parquet`）：STOCK_CODE, TRADE_DATE, CLOSE, VOL, AMOUNT, MV, TURN, NET_ASSET_VALUE, ROE_TTM, BORROW_BUY, BORROW_REPAY, INFLOW_RATE, RATING_GRADE, VAL_MV

## 快速开始

```bash
cd factor_system

# 1. 个股因子计算
python3 stock/stock_factor_builder.py

# 2. 全流程：行业因子 + Z-score + 分析
python3 industry/run_pipeline.py
```

## 配置文件

### `industry/run_config.json`

```json
{
  "industry_factors": { ... },
  "monthly_factors": { ... },
  "analysis": ["charts", "ic", "rr", "sig", "monthly"],
  "sub_period": {
    "from_file": "data/market_periods.json",
    "groups": ["bull", "bear", "consolidate"]
  }
}
```

#### industry_factors / monthly_factors

每个因子格式：`"因子名": {"cat": "分类", "label": "中文名"}`

**量价类（pv）**：

| 因子名 | 标签 | 说明 |
|--------|------|------|
| `up_ratio` | 上涨家数占比 | 收盘上涨个股占行业比例 |
| `strong_ratio` | 强势股占比 | 收盘 > 60日均线个股比例 |
| `vol_ratio` | 强势量能占比 | 成交量 > 20日去极值均值×1.06 |
| `ma8_pos_avg` | 八均线状态占比 | 8条Fibonacci均线位置状态均值 |
| `ma_bull` | 多头均线占比 | MA5 > MA10 > MA20 个股占比 |
| `ma_bear` | 空头均线占比 | MA5 < MA10 < MA20 个股占比 |
| `strong_fund_ratio` | 强势股资金占比 | 成交额前10%个股的成交额占比 |

**资金类（fund）**：

| 因子名 | 标签 | 说明 |
|--------|------|------|
| `margin_sum5` | 区间融资净买入 | 融资净买入 5 日滚动求和 |
| `etf_inflow_st` | 板块相关ETF净流入 | 行业 ETF 净流入 5 日均线 |

**行业类（ind）**：

| 因子名 | 标签 | 说明 |
|--------|------|------|
| `amt_divg` | 成交占比乖离率 | 板块成交额 / 全市场成交额 - 20日均值 |
| `tech_sync_rt` | 技术协同度 | 收盘 > 20日均线个股比例 |
| `break_cons_rt` | 突破一致性 | 收盘为 20 日最高个股比例 |
| `turn_pctl` | 换手率分位数 | MV 加权行业换手率的 250 天分位 |
| `diverge_5d` | 主力资金背离度 | 5日累计净流入 - 5日指数涨跌 |
| `margin_dir` | 融资盘方向 | 融资净买入变化率 3 日均线 |
| `pb_disp` | 估值离散度 | 行业 PB 的 5 年分位点的 20 日标准差 |
| `ret_divg` | 涨幅分化度 | 前 3 大市值股票涨幅 - 板块指数涨幅 |
| `mom_12m` | 动量因子 | 过去 12 月剔除近 1 月的行业指数累计收益 |

**低频月度类（monthly）**：

| 因子名 | 标签 | 说明 |
|--------|------|------|
| `roe_pctl` | 盈利景气度 | MV 加权 ROE 的 36 个月分位点 |
| `upg_cnt_rt` | 分析师上调比例（数量） | 评级上调个股占行业比例 |
| `upg_mv_rt` | 分析师上调比例（市值） | 评级上调个股的市值占比 |

#### analysis

可选分析脚本：

| 值 | 脚本 | 输出 |
|----|------|------|
| `charts` | `analyze_factors.py` | 因子分布直方图、时序折线图、行业均值柱状图 |
| `ic` | `analyze_factor_ic.py` | Rank IC（T+1/5/10/22）、十分组累计收益、IC 时序、多空曲线 |
| `rr` | `analyze_factor_rr.py` | 十分组胜率、多头/空头尾部赔率、胜率柱状图 |
| `sig` | `analyze_factor_sig.py` | 因子值分布与正态对比、ACF(1) 行业截面统计 |
| `monthly` | `analyze_factor_monthly.py` | 月度因子的 IC / 十分组收益 / 胜率赔率 / 峰度ACF |

分析支持覆盖模式：在因子配置中添加 `"overwrite": ["ic", "rr"]`，运行该分析类型时自动删除已有结果并重算。

```json
"margin_sum5": {"cat": "fund", "label": "区间融资净买入", "overwrite": ["ic"]}
```

#### sub_period

子区间分析支持两种配置方式：

**方式一：直接定义**

```json
"sub_period": {
  "groups": [{
    "suffix": "my_range",
    "ranges": [{"start": "20220101", "end": "20221231"}]
  }]
}
```

**方式二：引用外部文件（推荐）**

```json
"sub_period": {
  "from_file": "data/market_periods.json",
  "groups": ["bull", "bear", "consolidate"]
}
```

支持特性：
- 多段拼接：一个组内多个 range 自动拼接，跨区间分析
- `"beginning"` 表示数据起点，`"now"` 表示数据终点
- 子区间输出到独立目录 `output/factor_analysis_{suffix}/`

#### 数据文件：`data/market_periods.json`

预定义的牛熊震荡区间：

- **bull**：19990501~20010601, 20050601~20071001, 20081001~20090801, 20140701~20150601, 20190101~20210201, 20240901~至今
- **bear**：20010601~20050601, 20071001~20081001, 20090801~20140701, 20150601~20160101, 20210201~20240901
- **consolidate**：20160101~20190101

## 增量计算

系统支持三级增量：

| 阶段 | 增量逻辑 | 触发条件 |
|------|---------|---------|
| 个股因子 | `stock_factor_builder.py` 检查已有列 | mode="skip" 时跳过 |
| 行业因子 | `compute_industry_factors` 按列名判断 | 配置中的因子不在表中则计算 |
| 分析 | `analysis_base.py` 检查输出子目录 | `{factor_dir}/{check_subdir}/` 已存在则跳过 |

### 覆盖模式

| 模式 | 配置 | 作用范围 |
|------|------|---------|
| 单因子计算覆盖 | `"up_ratio": {"overwrite": ["compute"]}` | 只重算该因子，同时清除其分析目录 |
| 全局计算覆盖 | `"compute_overwrite": true` | 重算配置中所有因子，自动清除所有分析目录 |
| 全局分析覆盖 | `"analysis_overwrite": ["charts", "ic"]` | 清除所有因子的指定分析目录 |

pipeline 末尾自动生成跨因子汇总表 `output/result/factor_summary.csv`。

## 新增因子评价指标

系统已有 5 个分析脚本（charts / ic / rr / sig / monthly）。如需新增评价维度（如最大回撤、换手率、信息比等）：

### 步骤

1. 在 `analysis/` 下新建脚本（或直接修改要增加指标的现有脚本）

2. 实现 `factor_fn` 函数，签名固定：
```python
def new_metric_fn(df, col, cn_label, cat, base_path):
    """df: 单个因子的全时段数据
       col: 因子列名
       cn_label: 因子中文名
       cat: 因子分类
       base_path: 输出目录，如 output/factor_analysis/pv/up_ratio
    """
    metric_dir = f'{base_path}/new_metric'
    os.makedirs(metric_dir, exist_ok=True)
    # 计算逻辑 …
    # 保存图表 / txt / parquet
    print(f'  [{col}] 完成')
```

3. 实现 `main()` 函数，作为独立运行入口和被 `run_pipeline.py` 调用的统一入口：
```python
def main():
    df = pd.read_parquet('output/data_processed/industry_daily_ratio.parquet')
    from analysis_base import run_analysis
    run_analysis(df, new_metric_fn, 'industry', check_subdir='new_metric')
```

4. 在 `industry/run_pipeline.py` 的 `run_analysis()` 中注册：
```python
scripts = {
    …
    'new_metric': f'{base}/analysis/analyze_factor_new_metric.py',
}
```

5. 在 `industry/run_config.json` 的 `analysis` 列表中添加 `"new_metric"`

### 说明

- `factor_fn` 会被 `analysis_base.run_analysis` 循环调用，每个因子调一次
- 全量分析和子区间分析自动复用，无需额外处理
- `check_subdir='new_metric'` 保证增量跳过只检查本指标的输出目录，不与其他分析脚本冲突
- 月度因子分析同样适用，只需把 `factor_type` 改为 `'monthly'`、`date_col` 改为 `'ym'`

## 输出结构

```
output/
├── data_processed/
│   ├── factor_stock.parquet               个股因子表
│   ├── industry_daily_ratio.parquet       行业因子日度表
│   ├── industry_daily_ratio_z.parquet     截面 Z-score 表
│   └── industry_monthly_ratio.parquet     月度因子表
├── factor_analysis/
│   ├── pv/up_ratio/charts/   ic/   ret/   rr/   sig/
│   ├── fund/margin_sum5/...
│   ├── ind/amt_divg/...
│   └── monthly/roe_pctl/...
├── factor_analysis_bull/                  子区间牛市
├── factor_analysis_bear/                  子区间熊市
├── factor_analysis_consolidate/           子区间震荡
└── result/
    └── factor_summary.csv                 全部因子 × 周期汇总表
```

每个因子目录下的分析文件：

| 子目录 | 内容 |
|--------|------|
| `charts/` | `{因子}_{区间}_hist.png`, `_ts.png`, `_ind_bar.png` |
| `ic/` | `ic_ts.png`, `ic_dist.png`, `ic_cum.png`, `ic_comp.png`, `{因子}_ic.parquet` |
| `ret/` | `ret_decile.png`, `ret_decile_bar.png`, `ret_long_short.png` |
| `rr/` | `win_rate_decile.png`, `tail_odds.png`, `{因子}_rr.txt` |
| `sig/` | `{因子}_kurtosis.png`, `{因子}_sig.txt` |

## 新增因子流程

### 场景一：个股因子

新增一个在个股层面计算的指标（如新的 K 线形态）。

**步骤：**

1. 在 `stock/stock_factors_registry.py` 写函数，输入个股全量 DF，返回因子序列（Series）：

```python
def my_factor(df):
    # df 包含 STOCK_CODE, TRADE_DATE, CLOSE, VOL ... 等字段
    result = df.groupby('STOCK_CODE')['CLOSE'].transform(...)
    return result
```

2. 在 `STOCK_FACTORS` 字典注册：

```python
STOCK_FACTORS = {
    ...
    'my_factor': my_factor,
}
```

3. 在 `stock/stock_config.json` 添加：

```json
{"my_factor": {"mode": "skip"}}
```

4. 运行 `python3 stock/stock_factor_builder.py`

### 场景二：行业因子（简单均值）

将已有个股因子取行业均值作为行业因子。

**步骤：**

1. 在 `industry/factors_registry.py` 的 `FACTOR_FUNCTIONS` 字典添加一行：

```python
FACTOR_FUNCTIONS = {
    ...
    'my_industry_ratio': _stock_mean('my_factor', 'my_industry_ratio'),
}
```

`_stock_mean(个股列名, 行业因子名)` 自动做 `groupby(['industry_code', 'TRADE_DATE'])[个股列名].mean()`。

2. 在 `industry/run_config.json` 的 `industry_factors` 中添加：

```json
"my_industry_ratio": {"cat": "ind", "label": "自定义因子"}
```

### 场景三：行业因子（独立计算逻辑）

因子需要读取原始数据自行加工，不能通过对个股因子取均值得到。

**步骤：**

1. 在 `industry/factors_registry.py` 写独立函数：

```python
def my_custom_factor(mapping):
    data = pd.read_parquet(f'{data_dir}/stock_base.parquet',
                           columns=['STOCK_CODE', 'TRADE_DATE', ...])
    data = data.merge(mapping, on=['STOCK_CODE', 'TRADE_DATE'], how='inner')
    result = data.groupby(['industry_code', 'TRADE_DATE']).apply(...)
    return result[['industry_code', 'TRADE_DATE', 'my_custom_factor']]
```

函数签名可选参数：`fac`, `mapping`, `out_dir`。
结果必须包含 `industry_code` + `TRADE_DATE` + 因子列。

2. 在 `FACTOR_FUNCTIONS` 注册：

```python
'my_custom_factor': lambda fac, mapping, **kw: my_custom_factor(mapping),
```

3. 在 `industry/run_config.json` 添加，运行 `python3 industry/run_pipeline.py`

### 场景四：月度因子

和场景三类似，但结果以 `ym`（格式 `YYYYMM`）代替 `TRADE_DATE` 作为时间索引。

**步骤：**

1. 在 `industry/factors_registry.py` 写函数，返回 `[industry_code, ym, 因子列]`
2. 在 `FACTOR_FUNCTIONS` 注册
3. 在 `industry/run_config.json` 的 `monthly_factors` 中添加
4. `analysis` 列表包含 `"monthly"` 则自动参与分析

## 技术细节

- **运行环境**：Python 3.9+，依赖 pandas, numpy, scipy, matplotlib
- **个股因子**：在 `stock/stock_factors_registry.py` 注册，输入个股 DF 返回因子序列
- **行业因子**：在 `industry/factors_registry.py` 注册，支持 `_stock_mean` 模板（对个股因子取行业均值）或独立计算函数
- **分析框架**：`analysis/analysis_base.py` 统一管理因子循环、子区间多组、增量跳过
- **输出格式**：图片 150dpi，IC 数据存 parquet，统计指标存 txt
