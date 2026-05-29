"""个股因子页面。全套 widget，domain='stock' 硬编码。"""
import time
from factor_workbench.web_shared import *
# 以下 _ 开头的名字不会被 import * 带进来，显式补入
from factor_workbench.web_shared import (
    _disp_labels,
    _find_func, _get_func_code, _extract_func,
    _replace_factor, _run_scratch, _delete_factor,
    _build_req_summary, _refresh_data, refresh_df, _load_ai, _save_ai,
    _save_toc, _load_toc, _set_toc_items,
    _FACTORS,
)

def stock_page():
    """个股因子页面。"""
    DOMAIN = 'stock'
    _AI_KEY = f'ai_pending_{DOMAIN}'
    _NEXT_ID_KEY = f'ai_next_id_{DOMAIN}'
    _TOC_KEY = f'_toc_items_{DOMAIN}'

    st.session_state.setdefault(f'mode_{DOMAIN}', '')
    st.session_state.setdefault(f'search_key_{DOMAIN}', '')
    st.session_state.setdefault(_AI_KEY, [])
    st.session_state.setdefault(_NEXT_ID_KEY, 0)
    st.session_state.setdefault(_TOC_KEY, [])
    _load_ai(DOMAIN)
    _load_toc(DOMAIN)
    all_factors = refresh_df()[1]

    st.subheader('📈 个股因子')

    # ── 批量运行弹窗 ──
    _ds_cols = st.columns([1, 1])
    with _ds_cols[0]:
        with st.popover('批量运行'):
            _mode = st.radio('模式', ['skip', 'overwrite'], horizontal=True, key=f'batch_mode_{DOMAIN}')
            _dom_factors = [(k, v) for k, v in _FACTORS.items() if k.startswith(f'{DOMAIN}:')]
            _all_keys = [f'batch_dom_{k.replace(":", "_")}' for k, _ in _dom_factors]
            _gk = f'batch_all_{DOMAIN}'
            if '_prev_' + _gk not in st.session_state:
                st.session_state['_prev_' + _gk] = False
            _g_cur = st.checkbox('全选', key=_gk)
            _g_prev = st.session_state['_prev_' + _gk]
            if _g_cur != _g_prev:
                for _t in _all_keys:
                    st.session_state[_t] = _g_cur
            st.session_state['_prev_' + _gk] = _g_cur
            _sel_factors = []
            for (_bk, _bm), _k in zip(_dom_factors, _all_keys):
                if st.checkbox(f'{_bm.name} ({_bm.label})', key=_k):
                    _sel_factors.append(_bm)
            if st.button(f'执行 ({len(_sel_factors)} 个)'):
                _log_lines = [f'批量运行: {len(_sel_factors)} 个因子, 模式={_mode}']
                _t_start = time.time()
                # 合并所有因子代码到单个 temp 文件，一次 subprocess
                _combined = 'import pandas as pd, numpy as np\n'
                for _meta in _sel_factors:
                    _code = _get_func_code(_meta.name, 'factor', domain=_meta.domain)
                    if _code:
                        _combined += '\n' + _code + '\n'
                _force = _mode == 'overwrite'
                _t0 = time.time()
                _out, _err = _run_scratch(_combined, force=_force)
                _elapsed = time.time() - _t0
                for _meta in _sel_factors:
                    if _err and _meta.name in _err:
                        _log_lines.append(f'  [{_meta.name}] ❌ ({_elapsed:.1f}s)')
                    else:
                        _log_lines.append(f'  [{_meta.name}] ✅ ({_elapsed:.1f}s)')
                _t_total = time.time() - _t_start
                _log_lines.append(f'总耗时: {_t_total:.1f}s')
                st.session_state[f'ai_log_{DOMAIN}'] = '\n'.join(_log_lines)
                st.rerun()

    # ── 搜索 + 列表 ──
    _c1, _c2 = st.columns([4, 1])
    with _c1:
        with st.form(key=f'search_form_{DOMAIN}', border=False):
            _cols = st.columns([3, 1])
            with _cols[0]:
                q = st.text_input('🔍 搜索因子', placeholder='输入因子名、中文名或分类...',
                                 label_visibility='collapsed', key=f'search_input_{DOMAIN}')
            with _cols[1]:
                submitted = st.form_submit_button('搜索', use_container_width=True)
                if submitted:
                    st.session_state[f'mode_{DOMAIN}'] = 'search'
    with _c2:
        _cols = st.columns([3, 1])
        with _cols[0]:
            if st.button('因子列表', width='stretch'):
                st.session_state[f'mode_{DOMAIN}'] = 'list'
        with _cols[1]:
            if st.button('↻', help='同步 .py 文件的变更'):
                _FACTORS.clear()
                load_factor_modules(['factors'])
                st.rerun()

    _domain_filter = all_factors['domain'] == DOMAIN if 'domain' in all_factors.columns else pd.Series([True] * len(all_factors))
    _mode = st.session_state.get(f'mode_{DOMAIN}', '')
    q_lower = q.lower() if q else ''

    # ── 搜索模式 ──
    if _mode == 'search' and q_lower:
        matched = all_factors[
            _domain_filter &
            (all_factors['factor'].str.lower().str.contains(q_lower, na=False) |
             all_factors['label'].str.lower().str.contains(q_lower, na=False) |
             all_factors['cat'].str.lower().str.contains(q_lower, na=False))
        ]
        if not matched.empty:
            st.caption(f'搜索列表  共 {matched["factor"].nunique()} 个因子')
            show = matched[disp_cols].copy()
            show.columns = [_disp_labels[c] for c in disp_cols]
            for c in ['多头胜率']:
                if c in show.columns:
                    show[c] = show[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
            event = st.dataframe(show, hide_index=True, width='stretch',
                                 column_config={c: st.column_config.TextColumn(c, alignment='center') for c in show.columns},
                                 on_select='rerun', selection_mode='single-row',
                                 key=f'search_tbl_{DOMAIN}_{st.session_state.get(f"search_key_{DOMAIN}", "")}')
            if event and event.selection and event.selection.rows:
                idx = event.selection.rows[0]
                _sel_row = matched.iloc[idx]
                selected_name = _sel_row['factor']
                selected_domain = _sel_row.get('domain', '')
                _prev = st.session_state.get('_sel', '')
                st.session_state._sel = selected_name
                st.session_state[f'last_names_{DOMAIN}'] = [(selected_name, 'factor', selected_domain)]
                if selected_name != _prev:
                    st.session_state[f'should_scroll_{DOMAIN}'] = True
        else:
            st.caption(f'未找到含 "{q}" 的因子')

    # ── 列表模式 ──
    if _mode == 'list':
        all_show = all_factors[_domain_filter][disp_cols].copy()
        all_show = all_show.sort_values('factor')
        all_show.columns = [_disp_labels[c] for c in disp_cols]
        for c in ['多头胜率']:
            if c in all_show.columns:
                all_show[c] = all_show[c].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else '-')
        st.caption(f'因子列表  共 {all_show["因子名"].nunique()} 个因子')
        ev = st.dataframe(all_show, hide_index=True, width='stretch', height=400,
                         column_config={c: st.column_config.TextColumn(c, alignment='center') for c in all_show.columns},
                         on_select='rerun', selection_mode='single-row',
                         key=f'all_tbl_{DOMAIN}_{st.session_state.get(f"search_key_{DOMAIN}", "")}')
        if ev and ev.selection and ev.selection.rows:
            idx = ev.selection.rows[0]
            _all_names = all_show['因子名'].tolist()
            if idx < len(_all_names):
                _prev = st.session_state.get('_sel', '')
                st.session_state._sel = _all_names[idx]
                _a_row = all_show.iloc[idx]
                st.session_state[f'last_names_{DOMAIN}'] = [(_all_names[idx], 'factor', _a_row.get('领域', ''))]
                if _all_names[idx] != _prev:
                    st.session_state[f'should_scroll_{DOMAIN}'] = True

    # ── 功能 Tab ──
    _ai_tab1, _ai_tab2, _ai_tab3 = st.tabs(['🤖 LLM 生成', '✏️ DSL 输入', '📝 完整函数'])

    with _ai_tab1:
        st.markdown('**研报文本生成因子**')
        st.session_state.setdefault(f'ai_log_{DOMAIN}', '')
        _c_log = st.columns([3, 2])
        with _c_log[0]:
            st.caption('研报内容')
            report_text = st.text_area('研报内容', height=400, label_visibility='collapsed',
                                        placeholder='粘贴研报或因子想法...')
            _has_report = bool(report_text.strip())
            _gen_clicked = st.button('生成', key=f'ai_generate_{DOMAIN}', disabled=not _has_report)
            _toc_clicked = st.button('生成目录', key=f'ai_toc_{DOMAIN}', disabled=not _has_report)
        with _c_log[1]:
            st.caption('日志')
            _ai_log = st.session_state.get(f'ai_log_{DOMAIN}', '')
            st.text_area('日志', _ai_log, height=400, disabled=True, label_visibility='collapsed')
        st.markdown('<style>div:has(> textarea[aria-label="日志"]) textarea{font-size:13px!important;white-space:pre-wrap!important;word-break:break-all!important}</style>', unsafe_allow_html=True)

        if _gen_clicked:
            st.session_state[f'ai_gen_count_{DOMAIN}'] = st.session_state.get(f'ai_gen_count_{DOMAIN}', 0) + 1
            if st.session_state.get(f'ai_log_{DOMAIN}', ''):
                st.session_state[f'ai_log_{DOMAIN}'] = ''
                st.session_state['_gen_ready'] = True
                st.rerun()
            else:
                st.session_state['_gen_ready'] = True

        if _toc_clicked:
            st.session_state['_toc_pending'] = True
            st.rerun()
        if st.session_state.pop('_toc_pending', False):
            with st.spinner('提取因子目录...'):
                from factor_generator import generate_toc
                try:
                    _r = generate_toc(report_text)
                except Exception as _exc:
                    st.error(f'目录生成失败: {_exc}')
                    _r = None
                if _r and _r.error:
                    st.error(_r.error)
                elif _r and _r.factors:
                    _existing = st.session_state.get(_TOC_KEY, [])
                    _existing_names = {x['name'] for x in _existing}
                    _new_items = [{'name': f.name, 'label': f.label, 'domain': f.domain,
                                   'logic_summary': f.logic_summary}
                                  for f in _r.factors if f.name not in _existing_names]
                    if _new_items:
                        _set_toc_items(DOMAIN, _existing + _new_items)
                    st.toast(f'提取 {len(_r.factors)} 个因子，新增 {len(_new_items)} 个', icon='📋')
                    if _r.usage:
                        u = _r.usage
                        st.session_state[f'ai_log_{DOMAIN}'] = f'目录: {len(_r.factors)} 个因子，消耗 {u.get("total_tokens","-")} tokens'
                    st.rerun()

        if st.session_state.pop('_gen_ready', False):
            with st.spinner('LLM 分析中...'):
                import sys as _sys
                if BASE not in _sys.path:
                    _sys.path.insert(0, BASE)
                from factor_generator import generate
                try:
                    _r = generate(report_text)
                except Exception as _exc:
                    st.error(f'生成失败: {_exc}')
                    _r = None
                if _r and _r.error:
                    st.error(_r.error)
                elif _r:
                    ai_pending = st.session_state.get(_AI_KEY, [])
                    for _fi in _r.factors:
                        _id = st.session_state[_NEXT_ID_KEY]
                        st.session_state[_NEXT_ID_KEY] += 1
                        ai_pending.insert(0, {'id': _id, 'data': _fi})
                    st.session_state[_AI_KEY] = ai_pending
                    st.session_state[f'ai_pending_sel_{DOMAIN}'] = ai_pending[0]['id']
                    _save_ai(DOMAIN)
                    _rlog = _r.raw_llm_output or {}
                    _rtext = json.dumps(_rlog, ensure_ascii=False, indent=2) if _rlog else ''
                    st.session_state[f'ai_log_{DOMAIN}'] = (
                        f'生成 {len(_r.factors)} 个因子\n'
                        + '\n'.join(f'  [{f.domain}] {f.name} — {f.label}' for f in _r.factors)
                        + (f'\n\n--- LLM 原始输出 ---\n{_rtext[:10000]}' if _rtext else '')
                        + (f'\n\n用量: {_r.usage}' if _r.usage else ''))
                    if _r.usage:
                        u = _r.usage
                        st.toast(f'生成 {len(_r.factors)} 个因子，消耗 {u.get("total_tokens","-")} tokens', icon='🤖')
            st.rerun()

    with _ai_tab2:
        st.markdown('**直接输入 DSL 公式**')
        _dsl_l, _dsl_r = st.columns([3, 2])
        with _dsl_l:
            st.caption('DSL 公式')
            _manual_input = st.text_area('DSL 公式', height=400, label_visibility='collapsed',
                                          placeholder='例如: RANK(CLOSE / DELAY(CLOSE, 20) - 1)')
            _cc = st.columns([1, 1, 1, 1])
            _manual_code = st.session_state.get(f'_manual_code_{DOMAIN}', '')
            _manual_name = _cc[0].text_input('因子名称', placeholder='mom_20d', key=f'm_name_{DOMAIN}')
            _manual_label = _cc[1].text_input('标签', placeholder='20日动量排名', key=f'm_label_{DOMAIN}')
            _manual_compile = _cc[2].button('编译', key=f'manual_compile_{DOMAIN}', use_container_width=True)
            _manual_run = _cc[3].button('运行', key=f'manual_dsl_run_{DOMAIN}', use_container_width=True,
                                         disabled=not bool(_manual_code))
            if _manual_compile:
                if _manual_input.strip() and _manual_name.strip():
                    from factor_generator.dsl_codegen import compile_dsl
                    from factor_generator.generator import FactorInfo
                    try:
                        _code, _info = compile_dsl(
                            _manual_input.strip(), _manual_name.strip(),
                            DOMAIN, label=_manual_label.strip() or _manual_name.strip())
                        st.session_state[f'_manual_code_{DOMAIN}'] = _code
                        _manual_code = _code
                        _id = st.session_state[_NEXT_ID_KEY]
                        st.session_state[_NEXT_ID_KEY] += 1
                        _fi = FactorInfo(
                            name=_manual_name.strip(),
                            label=_manual_label.strip() or _manual_name.strip(),
                            category='pv', domain=DOMAIN,
                            dsl=_manual_input.strip(), code=_code,
                            fields_needed=_info,
                        )
                        with st.expander('完整函数代码', expanded=False):
                            st.code(_fi.code, language='python')
                        ai_pending = st.session_state.get(_AI_KEY, [])
                        ai_pending.insert(0, {'id': _id, 'data': _fi})
                        st.session_state[_AI_KEY] = ai_pending
                        _save_ai(DOMAIN)
                        st.toast('已加入待处理列表', icon='✅')
                    except Exception as _e:
                        st.error(f'编译失败: {_e}')
            if _manual_run and _manual_code:
                _out, _err = _run_scratch(_manual_code, force=True)
                st.session_state[f'_dsl_log_{DOMAIN}'] = _out
                if _err:
                    st.session_state[f'_dsl_log_{DOMAIN}'] += '\n--- 错误 ---\n' + _err
                st.rerun()
        with _dsl_r:
            st.caption('运行日志')
            _dsl_log = st.session_state.get(f'_dsl_log_{DOMAIN}', '')
            st.text_area('运行日志', _dsl_log, height=400, label_visibility='collapsed', disabled=True, key=f'dsl_log_{DOMAIN}')

    with _ai_tab3:
        st.markdown('**Python 函数代码编译运行**')
        _col_l, _col_r = st.columns([3, 2])
        with _col_l:
            st.caption('代码')
            _result = code_editor(TEMPLATE, lang='python', height='420px', key=f'factor_code_v1_{DOMAIN}',
                                  response_mode=['blur', 'debounce', 'update'],
                                  options={'showInvisibles': False, 'minimap': {'enabled': False}})
            code = _result.get('text') or TEMPLATE
            c1, c2, c3 = st.columns(3)
            with c1:
                _force_key = f'editor_force_{DOMAIN}'
                _replace_key = f'editor_replace_{DOMAIN}'
                force = st.checkbox('覆盖重算', key=_force_key, on_change=lambda: (
                    st.session_state.update(**{_replace_key: False}) if st.session_state.get(_force_key) and st.session_state.get(_replace_key) else None))
            with c2:
                replace = st.checkbox('覆盖写入', key=_replace_key, on_change=lambda: (
                    st.session_state.update(**{_force_key: False}) if st.session_state.get(_replace_key) and st.session_state.get(_force_key) else None))
            with c3:
                run = st.button('运行', width='stretch')
        with _col_r:
            st.caption('运行日志')
            log_text = st.session_state.get(f'tab3_log_{DOMAIN}', '')
            st.text_area('运行日志', value=st.session_state.get(f'_tab3_log_{DOMAIN}', ''),
                         height=420, label_visibility='collapsed', disabled=True)

        if run:
            _code = code
            _replace = replace
            st.session_state[f'_tab3_log_{DOMAIN}'] = ''
            st.session_state[f'last_names_{DOMAIN}'] = []
            if _code.strip():
                stdout, stderr = _run_scratch(_code, force=True)
                st.session_state[f'_tab3_log_{DOMAIN}'] = stdout
                if stderr:
                    st.session_state[f'_tab3_log_{DOMAIN}'] += '\n--- 错误 ---\n' + stderr
                _m = re.search(r"@factor\([^)]*name=['\"]([^'\"]+)['\"]", _code)
                if _m and stdout:
                    st.session_state[f'last_names_{DOMAIN}'] = [(_m.group(1), 'factor', DOMAIN)]
                    st.session_state[f'should_scroll_{DOMAIN}'] = True
                    if _replace and '完成' in stdout:
                        _replace_factor(_m.group(1), 'factor', _code, domain=DOMAIN)
            st.rerun()

    # ── 待处理因子 ──
    if st.session_state.get(f'ai_gen_count_{DOMAIN}', 0):
        st.caption(f'生成运行: {st.session_state[f"ai_gen_count_{DOMAIN}"]} 次')
    ai_pending = st.session_state.get(_AI_KEY, [])

    if ai_pending:
        st.markdown(f'**待处理因子 ({len(ai_pending)})**')
        _sel_key = f'ai_pending_sel_{DOMAIN}'
        if _sel_key not in st.session_state:
            st.session_state[_sel_key] = ai_pending[0]['id']
        _id2label = {p['id']: f"[{p['data'].name}] {p['data'].label}" for p in ai_pending}
        _sel_id = st.selectbox('选择因子', list(_id2label.keys()),
                                format_func=lambda i: _id2label[i], key=_sel_key)
        _item = next(p for p in ai_pending if p['id'] == _sel_id)
        _fi = _item['data']

        existing = get_factors(domain=_fi.domain).get(_fi.name)
        if existing:
            st.warning(f'同名因子 {_fi.name} 已存在于 {_fi.domain} domain')

        if _fi.dsl:
            st.markdown(f'```\n{_fi.dsl}\n```')
        elif _fi.formula:
            _formatted = sqlparse.format(_fi.formula, reindent=True, keyword_case='upper', indent_width=4)
            st.markdown(f'```sql\n{_formatted}\n```')
        elif _fi.code:
            st.code(_fi.code, language='python')

        _all_ok = all(r.status == 'available' for r in _fi.fields_needed)
        for r in _fi.fields_needed:
            tag = '✅' if r.status == 'available' else '❌'
            dest = f' → {r.table}.{r.field}' if r.table else ''
            st.markdown(f'{tag} {r.field}{dest}')

        _compiled_key = f'ai_compiled_{_sel_id}'
        _needs_compile = bool(_fi.dsl or _fi.formula)
        _already_compiled = st.session_state.get(_compiled_key, False)
        if _fi.code and (not _fi.dsl or _already_compiled):
            st.code(_fi.code, language='python')

        _btn_cols = st.columns([1, 2, 3, 1])
        with _btn_cols[0]:
            if _needs_compile:
                if st.button('编译', key=f'ai_compile_{_sel_id}'):
                    from factor_generator.compiler import compile_factor
                    try:
                        _fi.code = compile_factor(_fi)
                        st.session_state[_compiled_key] = True
                        _save_ai(DOMAIN)
                    except Exception as _e:
                        st.error(f'编译失败: {_e}')
                    st.rerun()
            else:
                st.button('编译', disabled=True, key=f'ai_compile_{_sel_id}')
        with _btn_cols[1]:
            if st.button('刷新数据', help='重新扫描数据目录，更新字段可用性'):
                _refresh_data(DOMAIN)
                st.rerun()
        _can_run = _already_compiled or (_fi.code and not _needs_compile)
        def _toggle_ai():
            if st.session_state[f'ai_force_{DOMAIN}'] and st.session_state[f'ai_replace_{DOMAIN}']:
                st.session_state[f'ai_replace_{DOMAIN}'] = False
        def _toggle_ai2():
            if st.session_state[f'ai_replace_{DOMAIN}'] and st.session_state[f'ai_force_{DOMAIN}']:
                st.session_state[f'ai_force_{DOMAIN}'] = False
        if _all_ok and _can_run:
            with _btn_cols[2]:
                _c = st.columns([1, 1, 1])
                _c[0].checkbox('覆盖重算', key=f'ai_force_{DOMAIN}', on_change=_toggle_ai)
                _c[1].checkbox('覆盖写入', key=f'ai_replace_{DOMAIN}', on_change=_toggle_ai2)
                if _c[2].button('运行', key=f'ai_run_{DOMAIN}'):
                    _ai_force = st.session_state.get(f'ai_force_{DOMAIN}', False)
                    _ai_replace = st.session_state.get(f'ai_replace_{DOMAIN}', False)
                    _stdout, _stderr = _run_scratch(_fi.code, force=_ai_force or _ai_replace)
                    st.session_state[f'_pending_run_log_{DOMAIN}'] = _stdout
                    if _stderr:
                        st.session_state[f'_pending_run_log_{DOMAIN}'] += '\n--- 错误 ---\n' + _stderr
                    if _ai_replace and _stdout and '完成' in _stdout:
                        _replace_factor(_fi.name, 'factor', _fi.code, domain=DOMAIN)
                    _FACTORS.clear()
                    load_factor_modules(['factors'])
                    st.session_state[f'last_names_{DOMAIN}'] = [(_fi.name, 'factor', _fi.domain)]
                    st.session_state[f'should_scroll_{DOMAIN}'] = True
                    ai_pending = [p for p in ai_pending if p['id'] != _sel_id]
                    st.session_state[_AI_KEY] = ai_pending
                    _save_ai(DOMAIN)
                    st.rerun()
        # 显式待办运行日志
        _run_log = st.session_state.get(f'_pending_run_log_{DOMAIN}', '')
        if _run_log:
            st.text_area('运行日志', value=_run_log, height=200, disabled=True, label_visibility='collapsed')

        with _btn_cols[3]:
            if st.button('删除', key=f'ai_del_{DOMAIN}'):
                ai_pending = [p for p in ai_pending if p['id'] != _sel_id]
                st.session_state[_AI_KEY] = ai_pending
                _save_ai(DOMAIN)
                st.rerun()

        # ── 全部运行弹窗 ──
        with st.popover(f'全部运行 ({len(ai_pending)})'):
            _non_dup_ids = [p['id'] for p in ai_pending if not get_factors(domain=p['data'].domain).get(p['data'].name)]
            _gk = f'ai_batch_all_{DOMAIN}'
            if '_prev_' + _gk not in st.session_state:
                st.session_state['_prev_' + _gk] = False
            _g_cur = st.checkbox('全选', key=_gk, disabled=not _non_dup_ids)
            _g_prev = st.session_state['_prev_' + _gk]
            if _g_cur != _g_prev:
                for _pid in _non_dup_ids:
                    st.session_state[f'ai_batch_{_pid}'] = _g_cur
            st.session_state['_prev_' + _gk] = _g_cur
            _dom_pending = {}
            for _p in ai_pending:
                _dom_pending.setdefault(_p['data'].domain, []).append(_p)
            _run_ids = []
            for _dom, _items in sorted(_dom_pending.items()):
                _non_dup_items = [p for p in _items if p['id'] in _non_dup_ids]
                if not _non_dup_items:
                    continue
                with st.expander(f'{_dom} ({len(_non_dup_items)})', expanded=False):
                    _dc = st.checkbox(f'全选 {_dom}', key=f'ai_dom_{_dom}')
                    _dp = st.session_state.get('_prev_' + f'ai_dom_{_dom}', False)
                    if _dc != _dp:
                        for _p in _non_dup_items:
                            st.session_state[f'ai_batch_{_p["id"]}'] = _dc
                    st.session_state['_prev_' + f'ai_dom_{_dom}'] = _dc
                    for _p in _items:
                        _is_dup = _p['id'] not in _non_dup_ids
                        if st.checkbox(f'{_p["data"].name} — {_p["data"].label}',
                                       key=f'ai_batch_{_p["id"]}', disabled=_is_dup) and not _is_dup:
                            _run_ids.append(_p['id'])
            if st.button(f'运行选中 ({len(_run_ids)})'):
                from factor_generator.compiler import compile_factor
                msgs = []
                for _rid in _run_ids:
                    _item = next(p for p in ai_pending if p['id'] == _rid)
                    _fi = _item['data']
                    try:
                        _code = compile_factor(_fi)
                        _out, _err = _run_scratch(_code, force=True)
                        if _err:
                            msgs.append(f'[{_fi.name}] ❌ {_err[:200]}')
                        else:
                            msgs.append(f'[{_fi.name}] ✅')
                    except Exception as _e:
                        msgs.append(f'[{_fi.name}] ❌ {_e}')
                st.session_state[f'ai_log_{DOMAIN}'] = '\n'.join(msgs)
                st.rerun()

        # ── 重复处理弹窗 ──
        _dup_list = [p for p in ai_pending if get_factors(domain=p['data'].domain).get(p['data'].name)]
        if _dup_list:
            _pop_st = st.session_state.get(f'dupe_popover_{DOMAIN}', {})
            _pop_open = isinstance(_pop_st, dict) and _pop_st.get('is_open', False)
            _pop_was = st.session_state.get(f'_pop_was_{DOMAIN}', False)
            if not _pop_open and _pop_was:
                st.session_state[f'_dupe_reset_{DOMAIN}'] = True
            st.session_state[f'_pop_was_{DOMAIN}'] = _pop_open
            with st.popover(f'重复处理 ({len(_dup_list)})', key=f'dupe_popover_{DOMAIN}'):
                if st.session_state.pop(f'_dupe_reset_{DOMAIN}', False):
                    for _p in _dup_list:
                        st.session_state.pop(f'dupe_name_{_p["id"]}', None)
                _dup_doms = {}
                for _p in _dup_list:
                    _dup_doms.setdefault(_p['data'].domain, []).append(_p)
                for _dom, _items in sorted(_dup_doms.items()):
                    with st.expander(f'⚠️ {_dom} ({len(_items)})', expanded=False):
                        for _p in _items:
                            _fi = _p['data']
                            st.markdown(f'**{_fi.name}** 待办因子:')
                            _formatted = sqlparse.format(_fi.formula, reindent=True, keyword_case='upper', indent_width=4)
                            st.code(_formatted, language='sql')
                            _existing_code = _get_func_code(_fi.name, 'factor', domain=_fi.domain)
                            if _existing_code:
                                st.caption('已存在:')
                                st.code(_existing_code, language='python')
                            _new_name = st.text_input('新名称', value=_fi.name, key=f'dupe_name_{_p["id"]}')
                            _name_changed = _new_name != _fi.name
                            _name_dup = _name_changed and bool(get_factors(domain=_fi.domain).get(_new_name))
                            _name_empty = _name_changed and not _new_name.strip()
                            if _name_dup:
                                st.warning(f'名称 {_new_name} 已被占用')
                            if _name_empty:
                                st.warning('名称不能为空')
                            _do_overwrite = st.checkbox('覆盖已有因子', key=f'dupe_over_{_p["id"]}')
                            _can_rename = _name_changed and not _name_dup and not _name_empty
                            cols_act = st.columns(3)
                            if _can_rename:
                                if cols_act[0].button('确认改名', key=f'dupe_rename_{_p["id"]}'):
                                    _fi.name = _new_name
                                    _save_ai(DOMAIN)
                                    st.rerun()
                            if cols_act[1].button('覆盖并运行', key=f'dupe_over_run_{_p["id"]}', disabled=not _do_overwrite):
                                from factor_generator.compiler import compile_factor
                                try:
                                    _code = compile_factor(_fi)
                                    _out, _err = _run_scratch(_code, force=True)
                                    if _err:
                                        st.session_state[f'ai_log_{DOMAIN}'] = f'[{_fi.name}] ❌ {_err[:200]}'
                                    else:
                                        _replace_factor(_fi.name, 'factor', _code, domain=DOMAIN)
                                        st.session_state[f'ai_log_{DOMAIN}'] = f'[{_fi.name}] ✅'
                                except Exception as _e:
                                    st.session_state[f'ai_log_{DOMAIN}'] = f'[{_fi.name}] ❌ {_e}'
                                st.rerun()
                            if cols_act[2].button('删除待办', key=f'dupe_del_{_p["id"]}'):
                                ai_pending = [x for x in ai_pending if x['id'] != _p['id']]
                                st.session_state[_AI_KEY] = ai_pending
                                _save_ai(DOMAIN)
                                st.rerun()

    # ── TOC 目录展示与批量生成 ──
    _toc_items = st.session_state.get(_TOC_KEY, [])
    if _toc_items:
        with st.expander(f'因子目录 ({len(_toc_items)})', expanded=False):
            _toc_cols = st.columns([2, 2, 1, 1])
            _toc_sel_all = _toc_cols[0].checkbox('全选', key=f'toc_sel_all_{DOMAIN}')
            if _toc_sel_all != st.session_state.get(f'_prev_toc_sel_all_{DOMAIN}', False):
                for _item in _toc_items:
                    st.session_state[f'toc_{DOMAIN}_{_item["name"]}'] = _toc_sel_all
            st.session_state[f'_prev_toc_sel_all_{DOMAIN}'] = _toc_sel_all
            _toc_selected = []
            for _item in _toc_items:
                _cols = st.columns([2, 2, 1, 1])
                _checked = _cols[0].checkbox(_item['name'], value=False, key=f'toc_{DOMAIN}_{_item["name"]}')
                _cols[1].write(_item['label'])
                _cols[2].write(_item['domain'])
                _cols[3].write(_item.get('logic_summary', '')[:30])
                if _checked:
                    _toc_selected.append(_item)
            if _toc_selected:
                _batch_size = st.slider('每批数量', 1, 10, 5, key=f'toc_batch_size_{DOMAIN}')
                if st.button(f'批量生成 ({len(_toc_selected)} 个)'):
                    _bs = st.session_state.get(f'toc_batch_size_{DOMAIN}', 5)
                    _total = len(_toc_selected)
                    _msgs = []
                    for _i in range(0, _total, _bs):
                        _batch = _toc_selected[_i:_i+_bs]
                        _names = [x['name'] for x in _batch]
                        _prompt = '请生成以下因子的完整 SQL 公式:\n'
                        for _x in _batch:
                            _prompt += f'  - {_x["name"]} ({_x["label"]}): {_x.get("logic_summary", "")}\n'
                        _prompt += f'\n研报原文:\n{report_text}'
                        try:
                            from factor_generator import generate
                            _r = generate(_prompt)
                            if _r and not _r.error and _r.factors:
                                for _fi in _r.factors:
                                    _id = st.session_state[_NEXT_ID_KEY]
                                    st.session_state[_NEXT_ID_KEY] += 1
                                    ai_pending = st.session_state.get(_AI_KEY, [])
                                    ai_pending.insert(0, {'id': _id, 'data': _fi})
                                    st.session_state[_AI_KEY] = ai_pending
                                _save_ai(DOMAIN)
                                _msgs.append(f'批 {_i//_bs+1}/{(len(_toc_selected)-1)//_bs+1}: {" ".join(_names)} ✅')
                            else:
                                _msgs.append(f'批 {_i//_bs+1}: {" ".join(_names)} ❌ {_r.error if _r else "空结果"}')
                        except Exception as _exc:
                            _msgs.append(f'批 {_i//_bs+1}: {" ".join(_names)} ❌ {_exc}')
                    st.session_state[f'ai_log_{DOMAIN}'] = '\n'.join(_msgs)
                    _processed_names = {x['name'] for x in _toc_selected}
                    _remaining = [x for x in _toc_items if x['name'] not in _processed_names]
                    if _remaining:
                        _set_toc_items(DOMAIN, _remaining)
                    else:
                        _set_toc_items(DOMAIN, [])
                    st.rerun()
            _toc_cols = st.columns([1, 1])
            if _toc_cols[0].button('清空目录'):
                _set_toc_items(DOMAIN, [])
                st.rerun()

    # ── 数据需求汇总 ──
    with st.expander('数据需求汇总'):
        _summary = _build_req_summary(ai_pending if ai_pending else [])
        if not _summary:
            st.caption('无数据需求信息')
        else:
            _total_missing = 0
            for table_name, fields in sorted(_summary.items()):
                _table_ok = all(f['status'] == 'available' for f in fields)
                tag = '✅' if _table_ok else '❌'
                st.markdown(f'**{tag} {table_name}**')
                for info in fields:
                    f_tag = '✅' if info['status'] == 'available' else '❌'
                    if info['status'] != 'available':
                        _total_missing += 1
                    _count = len(info['needed_by'])
                    _names = ', '.join(info['needed_by'])
                    st.markdown(f'&nbsp;&nbsp;{f_tag} {info["field"]} — {_count} 个因子（{_names}）')
            if _total_missing:
                st.caption(f'共 {_total_missing} 个字段缺失，补全数据后点"刷新数据"更新状态')

    st.markdown('<div id="factor-metrics"></div>', unsafe_allow_html=True)

    # ---- 展示选中因子的函数代码 + 删除 ----
    for _name, _kind, _dom in st.session_state.get(f'last_names_{DOMAIN}', []):
        from factor_workbench.engine.registry import get_factor as _gf
        _meta_fc = _gf(_name, _dom) if _dom else get_factors().get(_name)
        _found = _get_func_code(_name, _kind, domain=_dom or (_meta_fc.domain if _meta_fc else None))
        if _found:
            _bar = st.columns([20, 1])
            with _bar[1]:
                with st.popover('⋮'):
                    if st.button('删除', key=f'del_{DOMAIN}_{_name}'):
                        _delete_factor(_name, _dom)
                        st.rerun()
            st.code(_found, language='python')

    # ---- 显示结果 ----
    df, all_factors = refresh_df()
    names = st.session_state.get(f'last_names_{DOMAIN}', [])
    if names:
        for name, kind, dom in names:
            from factor_workbench.engine.registry import get_factor as _gf
            meta = _gf(name, dom) if dom else get_factors().get(name)
            if not meta:
                continue
            cat = meta.category
            domain = meta.domain
            func_code = _get_func_code(name, kind, domain=domain)
            _rebuild = [df is None or df[df['factor'] == name].empty]

            from config.domain_config import DOMAIN_CONFIG
            _dc = DOMAIN_CONFIG.get(domain, {}).get(meta.freq, {})
            _layout = _dc.get('display', {}).get('layout', [])

            for row in _layout:
                if not row:
                    continue
                item = row[0]

                if item and isinstance(item, str) and item.startswith('_title:'):
                    st.subheader(item[7:])
                elif item == '_table':
                    if df is not None and not df.empty and names:
                        from config.domain_config import DOMAIN_CONFIG as _DC
                        _ddc = _DC.get(domain, {}).get(meta.freq, {})
                        _dm = _ddc.get('display', {}).get('metrics', [])
                        _html = render_metrics_table(df, names, _dm)
                        if _html:
                            st.markdown(_html, unsafe_allow_html=True)
                elif len(row) == 1 and item in MULTI_CHARTS:
                    entry = CHART_MAP.get(item)
                    if entry is None:
                        continue
                    try:
                        data = entry[0](BASE, name, cat, domain=domain)
                        if data is not None:
                            figs = entry[1](data)
                            cols = st.columns(len(figs))
                            for (h, fig), col in zip(figs, cols):
                                with col:
                                    st.plotly_chart(fig, width='stretch', key=f'{name}_{item}_{h}')
                        else:
                            _rebuild[0] = True
                    except Exception:
                        _rebuild[0] = True
                else:
                    cols = st.columns(len(row))
                    for j, c_name in enumerate(row):
                        entry = CHART_MAP.get(c_name)
                        if entry is None:
                            continue
                        with cols[j]:
                            try:
                                data = entry[0](BASE, name, cat, domain=domain)
                                if data is not None:
                                    fig = entry[1](data, name)
                                    _label = re.search(r'_T(\d+)$', c_name)
                                    if _label:
                                        cur = fig.layout.title.text
                                        fig.update_layout(title=f"{cur}（持有{_label.group(1)}日）")
                                    st.plotly_chart(fig, width='stretch', key=f'{name}_{c_name}')
                                else:
                                    _rebuild[0] = True
                            except Exception:
                                _rebuild[0] = True

            if _rebuild[0] and func_code:
                st.info(f'{name} 部分分析数据缺失')
                if st.button('补全数据', key=f'rebuild_{DOMAIN}_{name}'):
                    with st.spinner('计算中...'):
                        stdout, stderr = _run_scratch(func_code, force=True)
                        st.session_state[f'_tab3_log_{DOMAIN}'] = stdout
                        if stderr:
                            st.session_state[f'_tab3_log_{DOMAIN}'] += '\n--- 错误 ---\n' + stderr
                        st.rerun()

        if st.session_state.pop(f'should_scroll_{DOMAIN}', False):
            st.html("""
            <script>document.getElementById('factor-metrics').scrollIntoView({behavior:'smooth',block:'start'})</script>
            <span style="display:none">""" + str(hash(str(st.session_state.get('_sc', 0)))) + """</span>
            """, unsafe_allow_javascript=True)
            st.session_state._sc = st.session_state.get('_sc', 0) + 1
