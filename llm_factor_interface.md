# LLM 因子生成接口

## 任务

读研报/想法 → 输出 `@factor` 代码 + 数据需求清单。

产出直接放入浏览器测试，不需要手动配置。

## @factor 装饰器

```python
@factor(name='因子英文名',
        category='分类',    # pv(价量) / fund(资金) / ind(行业) / monthly(月度)
        label='中文标签',
        domain='industry')  # industry / industry_monthly
def factor_name(api):
    ...
    return df
```

| domain | 说明 | key 列 |
|--------|------|--------|
| `industry` | 行业日频 | `industry_code`, `trade_date` |
| `industry_monthly` | 行业月度 | `industry_code`, `ym` |
| `stock` | 个股日频（中间量用） | `stock_code`, `trade_date` |

函数返回 DataFrame，必须包含 key 列 + 因子列。

**注意列名全小写下划线**：`stock_code`、`trade_date`、`close`、`amount`。SQL 里也是小写。

## 可用数据表

LLM 输出需标注每个字段的状态（`available`/`missing`/`need_derive`）：

### data/（原始数据）

| 表名 | 关键列 | 说明 |
|------|--------|------|
| `stock_daily` | `stock_code + trade_date` | 个股行情：close, vol, amount, turn, mv, pe_ttm 等 |
| `industry_price` | `industry_code + trade_date` | 行业指数：close, open |
| `etf_daily` | `etf_code + trade_date` | ETF 数据 |

### output/feature_library/（中间量）

| 表名 | 列 | 说明 |
|------|-----|------|
| `stock_features` | `stock_code + trade_date + industry_code + 各特征值` | 股票级特征 |

### 无对应字段时标注 missing

## 输出格式

### 因子代码

自包含的 Python 函数，只依赖 `api` 参数：

```python
@factor(name='ret_5d', category='pv', label='5日涨幅', domain='industry')
def ret_5d(api):
    return api.query("""
        SELECT industry_code, trade_date,
               (close / lag(close, 5) OVER w - 1) as ret_5d
        FROM industry_price
        WINDOW w AS (PARTITION BY industry_code ORDER BY trade_date)
    """)
```

### 数据需求清单

```yaml
data_requirements:
  - field: industry_price.close
    needed_for: "计算 5 日收益"
    status: available
  - field: stock_daily.amount
    needed_for: "计算行业成交额占比"
    status: available
```

## 集成流程

```
LLM 产出 @factor 代码
    ↓ 保存到 factors/llm/xxx.py
    ↓ 浏览器刷新后自动出现（load_factor_modules 自动扫描）
    ↓ 选中因子 → 补全数据 → 出图表
```

框架会自动扫描 `factors/` 和 `features/` 下的所有 `.py` 文件，产出的代码放进去就生效，不需要修改任何配置。

## 不负责

- 运行 pipeline
- 修改框架代码
- 提供原始数据
