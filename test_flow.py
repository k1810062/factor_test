import sys, json, yaml
sys.path.insert(0, '/Users/wby/k/factor_test/llm_factors')

from factor_generator.matcher import FieldMatcher
from factor_generator.generator import _parse_llm_output, _apply_code_mapping

# 加载数据字典
with open('/Users/wby/k/factor_test/llm_factors/factor_generator/config/data_dictionary.yaml') as f:
    data_dict = yaml.safe_load(f)

llm_output = {
  "factors": [{
    "name": "price1m",
    "label": "1月价格动量",
    "category": "pv",
    "domain": "stock",
    "code": "@factor(name='price1m', category='pv', label='1月价格动量', domain='stock')\ndef price1m(api):\n    \"\"\"\n    1月价格动量 = 当日收盘价 / mean(过去21天收盘价) - 1\n    衡量当前股价相对于过去一个月平均价格的偏离程度。\n    \"\"\"\n    # 获取个股日线行情数据\n    daily_data = api.table('stock_daily', fields=['STOCK_CODE', 'TRADE_DATE', 'close_price'])\n    \n    # 按股票分组，计算过去21日均价\n    daily_data = daily_data.sort_values(['STOCK_CODE', 'TRADE_DATE'])\n    daily_data['close_price_ma21'] = daily_data.groupby('STOCK_CODE')['close_price'].transform(lambda x: x.rolling(21).mean())\n    \n    # 计算Price1M\n    daily_data['price1m'] = daily_data['close_price'] / daily_data['close_price_ma21'] - 1\n    \n    # 返回key列+因子列\n    result = daily_data[['STOCK_CODE', 'TRADE_DATE', 'price1m']].copy()\n    result = result.dropna(subset=['price1m'])\n    return result\n",
    "logic_summary": "Price1M = 当日收盘价 / 过去21日均价 - 1，衡量股价短期动量，正值表示近期强势。",
    "aliases": {
      "stock_daily": {
        "type": "table",
        "description": "个股日线行情数据"
      },
      "stock_daily.close_price": {
        "type": "field",
        "description": "个股收盘价（后复权）"
      }
    }
  }]
}

print("=" * 60)
print("1. 解析 LLM 输出")
print("=" * 60)
parsed = _parse_llm_output(llm_output)
fi = parsed[0]
print(f"因子: {fi.name}")
print(f"domain: {fi.domain}")
print(f"data_requirements 数量: {len(fi.data_requirements)}")

print()
print("=" * 60)
print("2. 匹配数据字典")
print("=" * 60)
matcher = FieldMatcher(data_dict)
matcher.build_index()

req_dicts = [{'description': r.description} for r in fi.data_requirements]
matched = matcher.match(req_dicts)

table_map = {}
field_map = {}
for req, m in zip(fi.data_requirements, matched):
    print(f"  \"{m['description']}\"")
    print(f"    → {m['status']}, {m.get('matched_table','?')}.{m.get('matched_field','?')} (score: {m.get('confidence',0):.3f})")
    if m['status'] == 'available':
        if m.get('matched_table') and req.alias_table:
            table_map[req.alias_table] = m['matched_table']
        if m.get('matched_field') and req.alias_field:
            field_map[req.alias_field] = m['matched_field']

print(f"\n表名映射: {table_map}")
print(f"字段映射: {field_map}")

print()
print("=" * 60)
print("3. 代码替换结果")
print("=" * 60)
new_code = _apply_code_mapping(fi.code, table_map, field_map)
print(new_code)

print("=" * 60)
print("4. 最终数据需求清单")
print("=" * 60)
print(f"{'描述':25s} {'状态':12s} {'匹配字段'}")
print("-" * 55)
for r in fi.data_requirements:
    matched_t = f"{r.matched_table}.{r.matched_field}" if r.matched_table and r.matched_field else "-"
    print(f"  {r.description:25s} {r.status:12s} {matched_t}")
