"""从 parquet 读取因子分析结果，构造 Plotly 图表。

供 app.py 调用，不绑定 Streamlit，返回 Figure 对象。
"""

import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def _analysis_path(base_dir, domain, cat, name, suffix):
    """构造 domain 化的分析结果文件路径。"""
    return os.path.join(base_dir, f'output/analysis/{domain}/{cat}/{name}/{suffix}')


def load_ic_data(base_dir, name, cat, domain='industry'):
    """加载 IC parquet 数据，返回排序后的 DataFrame 或 None。"""
    path = _analysis_path(base_dir, domain, cat, name, f'ic/{name}_ic.parquet')
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    return df.sort_values('trade_date').reset_index(drop=True)


def load_ret_data(base_dir, name, cat, domain='industry', suffix=''):
    """加载十分组收益 parquet（支持后缀），返回 DataFrame 或 None。"""
    fn = f'ret/{name}_decile_rets{suffix}.parquet'
    path = _analysis_path(base_dir, domain, cat, name, fn)
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def data_exists(base_dir, name, cat, domain='industry'):
    """检查因子的 IC 和分组收益数据是否完整。"""
    ic_path = _analysis_path(base_dir, domain, cat, name, f'ic/{name}_ic.parquet')
    ret_path = _analysis_path(base_dir, domain, cat, name, f'ret/{name}_decile_rets.parquet')
    return os.path.exists(ic_path) and os.path.exists(ret_path)


def render_ic_cumulative(ic_df, name):
    """累计 Rank IC 图。"""
    horizons = [c for c in ic_df.columns if c != 'trade_date']
    fig = go.Figure()
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for h, color in zip(horizons, colors):
        vals = ic_df[h].dropna().cumsum()
        fig.add_trace(go.Scatter(x=vals.index, y=vals.values, mode='lines',
                                 name=h, line=dict(color=color, width=1.5)))
    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 累计 Rank IC',
                      hovermode='x unified', height=300,
                      margin=dict(l=10, r=10, t=30, b=10), showlegend=True)
    return fig


def render_long_short(ret_df, name):
    """多空收益图（根据实际组数动态适配）。"""
    n = len(ret_df.columns)
    cum = (1 + ret_df).cumprod() - 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cum.index, y=cum[n - 1], mode='lines',
                             name=f'多头(D{n})', line=dict(color='crimson', width=1.5)))
    fig.add_trace(go.Scatter(x=cum.index, y=cum[0], mode='lines',
                             name='空头(D1)', line=dict(color='steelblue', width=1.5)))
    fig.add_trace(go.Scatter(x=cum.index, y=cum[n - 1] - cum[0], mode='lines',
                             name=f'多空(D{n}-D1)', line=dict(color='darkgreen', width=2)))
    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 多空收益',
                      hovermode='x unified', height=300,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


def _lerp_hex(c1, c2, t):
    """线性插值两个 hex 颜色，t=0→c1, t=1→c2。"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f'#{r:02x}{g:02x}{b:02x}'


def _decile_colors(n):
    """生成 n 组分位颜色。n=10 完全还原原始配色，其他组数线性插值。"""
    _STOPS = ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59',
              '#ef6548', '#d73027', '#b30000', '#7f0000', '#4d0000']
    if n <= 1:
        return [_STOPS[0]]
    segs = len(_STOPS) - 1
    colors = []
    for i in range(n):
        pos = i * segs / (n - 1)
        seg = min(int(pos), segs - 1)
        t = pos - seg
        colors.append(_lerp_hex(_STOPS[seg], _STOPS[seg + 1], t))
    return colors


def render_decile_bar(ret_df, name):
    """分位数组日均收益柱状图。"""
    n = len(ret_df.columns)
    means = ret_df.mean() * 100
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[f'D{i+1}' for i in range(n)], y=means.values,
                         marker_color=_decile_colors(n)))
    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 分位数组日均收益',
                      xaxis_title='分组', yaxis_title='日均收益率(%)',
                      height=300, margin=dict(l=10, r=10, t=30, b=10))
    return fig


def render_win_rate(ret_df, name):
    """分位数组胜率柱状图。"""
    n = len(ret_df.columns)
    win_rates = (ret_df > 0).mean() * 100
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[f'D{i+1}' for i in range(n)], y=win_rates.values,
                         marker_color=_decile_colors(n)))
    fig.add_hline(y=50, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 十分组胜率',
                      xaxis_title='分组', yaxis_title='胜率(%)',
                      yaxis=dict(range=[0, 100]),
                      height=300, margin=dict(l=10, r=10, t=30, b=10))
    return fig


def render_ic_distribution(ic_df):
    """IC 分布直方图（每个 horizon 一个图）。

    返回 [(horizon_str, Figure)] 列表。
    """
    horizons = [c for c in ic_df.columns if c != 'trade_date']
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    results = []
    for idx, h in enumerate(horizons):
        vals = ic_df[h].dropna()
        mu, sigma = vals.mean(), vals.std()
        x_range = np.linspace(vals.min(), vals.max(), 100)
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=vals, histnorm='probability density',
                                   nbinsx=40, name=f'T+{h}',
                                   marker_color=colors[idx], opacity=0.7))
        fig.add_trace(go.Scatter(x=x_range,
                                 y=np.exp(-(x_range - mu) ** 2 / (2 * sigma ** 2))
                                   / (sigma * np.sqrt(2 * np.pi)),
                                 mode='lines', name='正态分布',
                                 line=dict(color='red', width=1.5)))
        fig.add_vline(x=mu, line_dash='dash', line_color='crimson', line_width=1.2)
        fig.update_layout(title=f'T+{h} IC 分布', height=250,
                          margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
        results.append((h, fig))
    return results


# ── 指标展示表 ──────────────────────────────────────

_METRIC_FMT = {
    'long_win': ('多头胜率', lambda v: f'{v*100:.1f}%'),
    'short_win': ('空头胜率', lambda v: f'{v*100:.1f}%'),
    'long_odds': ('多赔率', lambda v: f'{v:.2f}'),
    'short_odds': ('空赔率', lambda v: f'{v:.2f}'),
    'kurtosis': ('超额峰度', lambda v: f'{v:.2f}'),
}


def render_metrics_table(df, names, display_metrics):
    """展示所有周期的因子指标表（含 full + 各子区间）。返回 HTML 或 None。"""
    _names_only = [n for n, _ in names]
    fdf = df[df['factor'].isin(_names_only)]
    if fdf.empty:
        return None
    show = ['factor', 'period']
    for dm in display_metrics:
        if dm in fdf.columns:
            show.append(dm)
    tbl = fdf[show].copy()
    if tbl.empty:
        return None
    tbl = tbl.rename(columns={'period': '区间'})
    for c in tbl.columns:
        if c in ('factor', '区间'):
            continue
        if c in ('long_win', 'short_win'):
            tbl[c] = tbl[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
        elif c in ('long_odds', 'short_odds'):
            tbl[c] = tbl[c].apply(lambda x: f'{x:.2f}' if pd.notna(x) else '-')
        else:
            tbl[c] = tbl[c].apply(lambda x: f'{x:.4f}' if pd.notna(x) else '-')
    html = tbl.to_html(index=False, na_rep='-')
    html = html.replace('<table', '<table style="width:100%;table-layout:fixed;font-size:13px"')
    html = html.replace('<th>', '<th style="text-align:center">')
    html = html.replace('<td>', '<td style="text-align:center">')
    return html
