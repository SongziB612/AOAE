"""Prepare paper manual tickets or reconcile normalized fill CSV, without a broker."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from aoae.manual_ticket import prepare, reconcile, seal


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['prepare', 'reconcile'])
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--fills', type=Path)
    p.add_argument('--now', help='Explicit replay time for engineering tests only; omitted uses current UTC')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = args.output.resolve()
    if not target.is_relative_to(root) or target.exists() or target.with_suffix('.md').exists():
        raise ValueError('new workspace output required')
    now = args.now or datetime.now(timezone.utc).isoformat()
    request = json.loads(args.input.read_text(encoding='utf-8'))
    if args.mode == 'prepare':
        result = prepare(request, now)
    else:
        if not args.fills:
            p.error('--fills is required for reconcile')
        with args.fills.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        result = reconcile(request, rows, now)
        result['input_rows_sha256'] = seal(rows)
    if args.now:
        # Outside the sealed ticket so execution inputs cannot be changed silently.
        clock_note = '指定时钟重放；不是当前交易清单。'
    else:
        clock_note = '按当前时钟检查；不是实盘授权。'
    lines = ['# 人工执行工作单', '', clock_note, '', '状态：' + result['status'], '',
             '本工具不连接券商，不下单、不自动撤单；所有清单仅供纸面演练。', '']
    if args.mode == 'prepare':
        lines += ['有效截止：' + result.get('expires_at', '无（没有可用信号）'), '',
                  '| 代码 | 方向 | 份数 | 限价 | 预计佣金 |', '|---|---|---:|---:|---:|']
        lines += [f"| {l['symbol']} | {l['side']} | {l['quantity']} | {l['limit_price']} | {l['estimated_commission_cny']} |" for l in result['legs']]
        if not result['legs']:
            lines += ['', '没有下单条目。不得从历史回测复制买卖指令。']
        lines += ['', '阻断原因：' + '; '.join(result.get('blockers', [])), '',
                  '过期后应检查并撤销未成交委托，确认撤单成功；不得盲目补单。']
    else:
        lines += ['核对异常：' + '; '.join(result['violations']), '',
                  '费用合计：' + result['reported_total_fees_cny'], '',
                  '成交导入不等于券商认证；异常账本不可用于下一张清单。']
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with target.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')
    print(result['status'], target)
    return 1 if result['status'] == 'VIOLATION' else 0


if __name__ == '__main__':
    raise SystemExit(main())
