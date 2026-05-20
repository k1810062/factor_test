"""分析统一入口。自动对所有因子类型运行配置的分析。"""
import json, time
from analysis import load_data, run_analysis, chart_fn, ic_ret_fn, rr_fn, sig_fn

FUNCTIONS = {
    'charts': chart_fn,
    'ic': ic_ret_fn,
    'rr': rr_fn,
    'sig': sig_fn,
}


def main():
    cfg = json.load(open('industry/run_config.json'))
    analysis_list = cfg.get('analysis', [])

    for factor_type in ('industry', 'monthly'):
        if not cfg.get(f'{factor_type}_factors'):
            continue
        date_col = 'ym' if factor_type == 'monthly' else 'TRADE_DATE'
        df = load_data(factor_type)
        for name in analysis_list:
            if name not in FUNCTIONS:
                continue
            t0 = time.time()
            print(f'\n=== {factor_type} {name} 分析 ===')
            run_analysis(df, FUNCTIONS[name], factor_type,
                         date_col=date_col, check_subdir=name)
            print(f'  [{name}] 耗时: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
