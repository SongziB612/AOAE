"""One-command read-only export from the actual shadow journal to a paper ticket."""
import argparse
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

from aoae.manual_bridge import read_shadow, prepare_from_journal
from aoae.research_freeze import verify_freeze


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--snapshot', type=Path, help='Fresh account/quotes JSON, no account credentials')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.exists() or output.with_suffix('.md').exists():
        raise ValueError('new workspace output required')
    result = {'status': 'BLOCKED', 'legs': [], 'capital_authorized': False, 'orders_authorized': False}
    try:
        freeze = json.loads((root/'research/prospective/0003-raw-price-300k-paired-forward/freeze.json').read_text())
        if verify_freeze(root, freeze)['status'] != 'INTACT':
            raise ValueError('frozen files changed')
        audit = read_shadow(root/'data/runtime/paired_forward/engineering-shadow-v1.sqlite3')
        fees = json.loads((root/'research/manual_execution/account-fees-user-confirmed-v1.json').read_text())
        snapshot = json.loads(args.snapshot.read_text(encoding='utf-8')) if args.snapshot else None
        result = prepare_from_journal(root, audit, freeze, fees, snapshot, datetime.now(timezone.utc).isoformat())
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        result['reason'] = str(exc)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    lines = ['# 当前人工工作单', '', '状态：' + result['status'], '',
             '仅纸面核对，不是实盘授权。来自只读前向账本；不自动下单或撤单。', '',
             '有效截止：' + result.get('expires_at', '无'), '',
             '| 代码 | 方向 | 份数 | 限价 |', '|---|---|---:|---:|']
    lines += [f"| {l['symbol']} | {l['side']} | {l['quantity']} | {l['limit_price']} |" for l in result['legs']]
    if not result['legs']:
        lines += ['', '无下单条目。' + result.get('reason', '')]
    lines += ['', '未成交不得自动补单；到期需人工核对委托和撤单状态。']
    with output.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    print(result['status'], output)
    return 1 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
