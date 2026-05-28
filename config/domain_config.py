"""Domain 配置。
  - key_col / freq
  - analysis_groups：运行哪些分析组
  - display：展示配置（metrics 列、layout 行布局）
    _table=指标展示表（含全周期+子区间）、_title:xxx=标题
"""

DOMAIN_CONFIG = {
    'stock': {
        'key_col': 'stock_code',
        'freq': 'daily',
        'analysis_groups': ['ic', 'decile', 'sig', 'rr', 'ts'],
        'display': {
            'metrics': ['ic_T1', 'icir_T1',
                'ic_T5', 'icir_T5', 'ic_T10', 'icir_T10', 'ic_T22', 'icir_T22',
                'long_win', 'short_win', 'kurtosis'],
            'layout': [
                ['_table'],
                ['_title:因子表现'],
                ['ic_cumulative', 'long_short_T1'],
                ['_title:5日调仓'],
                ['decile_bar_T5', 'long_short_T5'],
                ['_title:10日调仓'],
                ['decile_bar_T10', 'long_short_T10'],
                ['_title:22日调仓'],
                ['win_rate_T22', 'long_short_T22'],
                ['_title:IC 分布'],
                ['ic_distribution'],
            ],
        },
        'ic': {'horizons': [1, 5, 10, 22], 'ann_factor': 252**0.5},
        'decile': {'n_groups': 10, 'horizons': [1, 5, 10, 22]},
        'sig': {},
        'rr': {'ret_horizon': 1},
        'ts': {'show_industry_bar': False},
    },
    'industry': {
        'key_col': 'industry_code',
        'freq': 'daily',
        'analysis_groups': ['ic', 'decile', 'sig', 'rr', 'ts'],
        'display': {
            'metrics': ['ic_T1', 'icir_T1',
                'ic_T5', 'icir_T5', 'ic_T10', 'icir_T10', 'ic_T22', 'icir_T22',
                'long_win', 'short_win', 'kurtosis'],
            'layout': [
                ['_table'],
                ['_title:因子表现'],
                ['ic_cumulative', 'long_short_T1'],
                ['_title:5日调仓'],
                ['decile_bar_T5', 'long_short_T5'],
                ['_title:IC 分布'],
                ['ic_distribution'],
            ],
        },
        'ic': {'horizons': [1, 5, 10, 22], 'ann_factor': 252**0.5},
        'decile': {'n_groups': 10, 'horizons': [1, 5]},
        'sig': {},
        'rr': {'ret_horizon': 1},
        'ts': {'show_industry_bar': True},
    },
    'industry_monthly': {
        'key_col': 'industry_code',
        'freq': 'monthly',
        'analysis_groups': ['ic'],
        'display': {
            'metrics': ['ic_T1', 'icir_T1'],
            'layout': [
                ['_table'],
                ['ic_cumulative'],
            ],
        },
        'ic': {'horizons': [1], 'ann_factor': 12**0.5},
    },
    'stock_monthly': {
        'key_col': 'stock_code',
        'freq': 'monthly',
        'analysis_groups': ['ic', 'sig'],
        'display': {
            'metrics': ['ic_T1', 'icir_T1', 'kurtosis'],
            'layout': [
                ['_table'],
                ['ic_cumulative'],
            ],
        },
        'ic': {'horizons': [1], 'ann_factor': 12**0.5},
        'sig': {},
    },
}
