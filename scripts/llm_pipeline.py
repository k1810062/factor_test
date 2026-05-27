"""LLM 因子全流程：读研报 → 生成 → 匹配 → 审查 → 运行。

用法：
    python3 scripts/llm_pipeline.py "研报内容"
    python3 scripts/llm_pipeline.py --file report.txt
"""

import argparse
import os
import subprocess
import sys
import tempfile

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.dirname(_SCRIPT_DIR)
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


def main():
    parser = argparse.ArgumentParser(description='LLM 因子全流程')
    parser.add_argument('report', nargs='?', help='研报文本')
    parser.add_argument('--file', help='研报文件路径')
    args = parser.parse_args()

    report = args.report
    if args.file:
        with open(args.file, encoding='utf-8') as f:
            report = f.read()
    if not report:
        parser.print_help()
        return

    from factor_generator import generate

    print('=' * 50)
    print('1. LLM 因子生成')
    print('=' * 50)
    result = generate(report)

    if result.error:
        print(f'\n[错误] {result.error}')
        sys.exit(1)
    if not result.factors:
        print('\n未生成任何因子')
        return

    if result.usage:
        u = result.usage
        print(f'\n生成 {len(result.factors)} 个因子，消耗 {u.get("total_tokens", "-")} tokens (输入 {u.get("prompt_tokens", "-")} + 输出 {u.get("completion_tokens", "-")})')

    # 因子状态 + 交互模式选择
    print('\n' + '=' * 50)
    print('2. 因子审查')
    print('=' * 50)
    import glob as _g
    to_run = []
    blocked = []

    for fi in result.factors:
        missing = [r for r in fi.fields_needed if r.status != 'available']
        if missing:
            blocked.append((fi, missing))
            print(f'\n❌ [{fi.domain}] {fi.name} ({fi.label}) — 缺数据')
            print(f'  逻辑: {fi.logic_summary}')
            if fi.formula:
                print(f'  SQL:\n{fi.formula}')
            elif fi.code:
                print(f'  代码:\n{fi.code}')
            for r in fi.fields_needed:
                tag = '✅' if r.status == 'available' else '❌'
                print(f'  {tag} {r.table}.{r.field}')
            continue

        print(f'\n[{fi.domain}] {fi.name} ({fi.label})')
        print(f'  逻辑: {fi.logic_summary}')
        if fi.formula:
            print(f'  SQL:\n{fi.formula}')
        elif fi.code:
            print(f'  代码:\n{fi.code}')
        if fi.fields_needed:
            for r in fi.fields_needed:
                tag = '✅' if r.status == 'available' else '⚠️'
                dest = f' → {r.table}.{r.field}' if r.table else ''
                print(f'  {tag} {r.field}{dest}')

        # 查重
        _dup = False
        for _f in sorted(_g.glob(f'{_BASE}/factors/*.py')):
            if f"@factor(name='{fi.name}'" in open(_f).read():
                _dup = True
                break
        if _dup:
            print(f'  ⚠️ 同名因子已在 {_f} 中存在')
            mode = input(f'  模式 [s]跳过已有 [o]覆盖重算 (s/o): ').strip().lower()
            to_run.append((fi, mode == 'o'))
        else:
            to_run.append((fi, False))  # skip 模式，新因子也会自动计算

    if blocked:
        print('\n' + '=' * 50)
        print('以下因子缺少数据，需补充后重试：')
        for fi, missing in blocked:
            print(f'  ❌ [{fi.domain}] {fi.name}')
            for m in missing:
                print(f'    缺: {m.table}.{m.field}')

    if not to_run:
        print('\n无待运行因子，退出')
        return

    print('\n' + '=' * 50)
    print('3. 运行确认')
    print('=' * 50)
    for fi, force in to_run:
        mode = '覆盖重算' if force else '跳过'
        print(f'  [{fi.domain}] {fi.name} — {mode}')

    try:
        confirm = input('\n是否运行以上因子？(y/N): ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = 'n'
    if confirm != 'y':
        print('已取消')
        return

    # 运行
    from factor_generator.compiler import compile_factor
    for fi, force in to_run:
        print(f'\n运行 [{fi.domain}] {fi.name}...')
        code = compile_factor(fi)  # 编译 formula → @factor 代码
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(code)
        tmp_path = tmp.name
        tmp.close()

        cmd = [sys.executable, '-m', 'factor_workbench.scratch', tmp_path]
        if force:
            cmd.insert(-1, '--force')
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=_BASE)
        os.unlink(tmp_path)

        if proc.returncode == 0:
            print(f'  ✅ {fi.name} 完成')
        else:
            print(f'  ❌ {fi.name} 失败: {proc.stderr[:200] if proc.stderr else "未知错误"}')

        for line in proc.stdout.split('\n'):
            kw = ('保存', '完成', '耗时', '需计算', '覆盖', '已加入')
            if any(k in line for k in kw):
                print(f'    {line}')


if __name__ == '__main__':
    main()
