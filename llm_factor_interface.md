# LLM 因子生成接口

## 1. 项目框架

量化因子研究框架，核心组件：

```
factor_system/
├── framework/          # 框架层（不动）
│   ├── data_api.py     # 数据访问 API
│   ├── registry.py     # @factor / @metric 装饰器
│   └── pipeline.py     # 统一调度
├── factors/            # 因子实现（LLM 产出放这里）
├── config/
│   └── config.json     # 因子注册
├── data/               # 原始数据（独立维护）
└── output/             # 分析结果
```

框架与数据解耦：因子函数只认 `api.query()` / `api.table()`，不直接读写文件。

---

## 2. @factor 装饰器

```python
@factor(name='因子英文名',
        category='分类',    # pv / fund / ind / monthly
        label='中文标签',
        domain='industry')  # industry / stock / monthly
def factor_name(api):
    ...
    return df
```

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `name` | 因子英文名，蛇形命名 | `ret_5d`, `mom_12m` 等 |
| `category` | 分类标签 | `pv`(价量) / `fund`(资金) / `ind`(行业) / `monthly`(月度) |
| `label` | 中文名 | 如 `"5日涨幅"` |
| `domain` | 计算域 | `industry`(行业日频) / `stock`(个股日频) / `monthly`(月度) |

函数接收 `api` 参数，返回 **包含 key 列 + 因子列的 DataFrame**。

---

## 3. DataAPI

两种数据访问方式：

### 3.1 api.query()

写 SQL，DuckDB 引擎执行。适用于复杂计算。

```python
def factor_name(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
```

- SQL 是 DuckDB 方言，支持窗口函数、聚合
- 表名从数据注册中心读取（见 §5 数据字典）
- 可以随意 JOIN

### 3.2 api.table()

直接读 DataFrame，适用于 pandas 计算。

```python
def factor_name(api):
    df = api.table('industry_daily',
                   columns=['industry_code', 'TRADE_DATE', 'amount', 'volume'])
    # ... pandas 处理 ...
    return result
```

- 不传 `columns` 则返回全部列
- pandas 处理完后返回 DataFrame，必须包含 key 列

### 3.3 返回值要求

DataFrame 必须包含 domain 对应的 key 列（见下表），加上因子列。一列因子值，列名即因子名。

| domain | key 列 | 日期列 |
|--------|--------|--------|
| `industry` | `industry_code`, `TRADE_DATE` | TRADE_DATE (YYYYMMDD 字符串) |
| `stock` | `STOCK_CODE`, `TRADE_DATE` | TRADE_DATE (YYYYMMDD 字符串) |
| `monthly` | `industry_code`, `ym` | ym (YYYYMM 字符串) |

---

## 4. 示例因子

### 简单因子（SQL）

```python
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT STOCK_CODE as industry_code, TRADE_DATE,
               (CLOSE / LAG(CLOSE, 5) OVER w - 1) as ret_5d
        FROM swi_daily
        WINDOW w AS (PARTITION BY STOCK_CODE ORDER BY TRADE_DATE)
    """)
```

### 复杂因子（pandas）

```python
@factor(name='up_ratio', category='pv', label='上涨家数占比', domain='industry')
def up_ratio(api):
    df = api.table('industry_daily',
                   columns=['industry_code', 'TRADE_DATE', 'up_stock'])
    return df.groupby(['industry_code', 'TRADE_DATE'])['up_stock'] \
             .mean().reset_index(name='up_ratio')
```

---

## 5. 数据字典（模板）

由人工维护，LLM 输出时标注数据覆盖情况。

### 模板格式

```yaml
tables:
  - name: swi_daily
    label: 申万行业指数日线
    desc: 行业指数每日行情
    fields:
      - {name: STOCK_CODE, type: VARCHAR, desc: "行业代码"}
      - {name: TRADE_DATE, type: VARCHAR, desc: "交易日 YYYYMMDD"}
      - {name: CLOSE, type: DOUBLE, desc: "收盘价"}
      # ...
  - name: industry_daily
    label: 行业成分股聚合数据
    desc: 行业维度每日聚合指标
    fields:
      - {name: industry_code, type: VARCHAR, desc: "行业代码"}
      - {name: TRADE_DATE, type: VARCHAR, desc: "交易日 YYYYMMDD"}
      - {name: amount, type: DOUBLE, desc: "成交金额"}
      # ...
```

### **输出要求：LLM 必须同时输出一份数据需求清单**

```yaml
data_requirements:
  - field: swi_daily.CLOSE
    needed_for: "ret_5d 计算收益"
    status: available    # available / missing / need_derive
  - field: some_table.some_field
    needed_for: "某因子计算"
    status: missing
    note: "需要从原始数据中提取"
```

---

## 6. LLM 输出规范

LLM 对输入（研报/想法）的分析结果，输出两部分：

### 6.1 因子代码

- Python 文件，`@factor` 装饰
- 可直接放入 `factors/` 目录
- 代码自包含，只依赖 `api` 参数

### 6.2 数据需求清单

标注每个所需数据的覆盖状态。用于：
- 判断因子是否可直接运行
- 汇总缺失数据，统一补充

### 6.3 批量模式

一篇研报含多个因子时：
- 输出多个 `.py` 文件
- 数据需求清单合并，去重汇总

---

## 7. 集成流程

```
研报/想法
    → LLM 分析
    → 输出因子代码 + 数据需求清单
    → 人工审核（展示界面 TODO）
    → 确认 → 代码放入 factors/ + config 注册 → pipeline 运行
    → 缺数据 → 补充数据 → 重跑
```

当前阶段：LLM 输出到 `output/llm_factors/` 目录，人工审核后移入 `factors/`。

---

## 8. 任务范围

这个文档定义的是 **LLM 因子生成模块与因子框架之间的接口**。LLM 窗口负责：

1. 读入研报/想法文本
2. 识别因子逻辑，输出 `@factor` 代码
3. 输出数据需求清单
4. 支持批量产出

不负责：
- 运行 pipeline
- 修改框架代码
- 补充原始数据
