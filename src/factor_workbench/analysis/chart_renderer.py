"""从 parquet 读取因子分析结果，构造 Plotly 图表。

供 app.py 调用，不绑定 Streamlit，返回 Figure 对象。
"""

import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def load_ic_data(base_dir, name, cat):
    """加载 IC parquet 数据，返回排序后的 DataFrame 或 None。"""
    path = os.path.join(base_dir,
                        f'output/factor_analysis/{cat}/{name}/ic/{name}_ic.parquet')
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    return df.sort_values('trade_date').reset_index(drop=True)


def load_ret_data(base_dir, name, cat):
    """加载十分组收益 parquet，返回 DataFrame 或 None。"""
    path = os.path.join(base_dir,
                        f'output/factor_analysis/{cat}/{name}/ret/{name}_decile_rets.parquet')
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def data_exists(base_dir, name, cat):
    """检查因子的 IC 和分组收益数据是否完整。"""
    ic_path = os.path.join(base_dir,
                           f'output/factor_analysis/{cat}/{name}/ic/{name}_ic.parquet')
    ret_path = os.path.join(base_dir,
                            f'output/factor_analysis/{cat}/{name}/ret/{name}_decile_rets.parquet')
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
    """多空收益图。"""
    cum = (1 + ret_df).cumprod() - 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cum.index, y=cum[9], mode='lines',
                             name='多头(D10)', line=dict(color='crimson', width=1.5)))
    fig.add_trace(go.Scatter(x=cum.index, y=cum[0], mode='lines',
                             name='空头(D1)', line=dict(color='steelblue', width=1.5)))
    fig.add_trace(go.Scatter(x=cum.index, y=cum[9] - cum[0], mode='lines',
                             name='多空(D10-D1)', line=dict(color='darkgreen', width=2)))
    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 多空收益',
                      hovermode='x unified', height=300,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


def render_decile_bar(ret_df, name):
    """十分组日均收益柱状图。"""
    means = ret_df.mean() * 100
    bar_colors = ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59',
                  '#ef6548', '#d73027', '#b30000', '#7f0000', '#4d0000']
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[f'D{i+1}' for i in range(10)], y=means.values,
                         marker_color=bar_colors))
    fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=0.6)
    fig.update_layout(title=f'{name} 十分组日均收益',
                      xaxis_title='分组', yaxis_title='日均收益率(%)',
                      height=300, margin=dict(l=10, r=10, t=30, b=10))
    return fig


def render_win_rate(ret_df, name):
    """十分组胜率柱状图。"""
    win_rates = (ret_df > 0).mean() * 100
    bar_colors = ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59',
                  '#ef6548', '#d73027', '#b30000', '#7f0000', '#4d0000']
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[f'D{i+1}' for i in range(10)], y=win_rates.values,
                         marker_color=bar_colors))
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
