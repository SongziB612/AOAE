"""Scheduled/offline dispatch of reviewed shadow inputs and durable comparison."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from aoae.forward_journal import ForwardJournal
from aoae.paired_workflow import run_workflow
from aoae.research_freeze import verify_freeze
from aoae.shadow_cycle import reduce_shadow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('use a new workspace output path')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'status': 'BLOCKED_REVIEW_REQUIRED', 'capital_authorized': False}
    try:
        freeze = json.loads((root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json').read_text(encoding='utf-8'))
        if verify_freeze(root, freeze)['status'] != 'INTACT':
            raise ValueError('frozen strategy changed')
        calendar = json.loads((root / 'configs/cn_exchange_calendar_2026.json').read_text(encoding='utf-8'))
        journal = ForwardJournal(root / 'data/runtime/paired_forward/engineering-shadow-v1.sqlite3', reducer=reduce_shadow)
        result = run_workflow(root, args.as_of, calendar, journal, freeze, datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        result['source_sha256'] = {name: sha256((root / name).read_bytes()).hexdigest() for name in (
            'scripts/run_paired_strategy_cycle.py', 'src/aoae/paired_workflow.py',
            'src/aoae/reviewed_day.py', 'src/aoae/reviewed_signal.py',
            'src/aoae/corporate_action_guard.py', 'configs/forward_action_anchors.json',
            'src/aoae/forward_journal.py', 'src/aoae/shadow_cycle.py',
            'src/aoae/shadow_accounting.py', 'configs/cn_exchange_calendar_2026.json')}
        with output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        print(json.dumps({'status': result['status'], 'report': str(output), 'blockers': result.get('blockers', [])}))
    return 0 if result['status'] == 'WORKFLOW_PASS_NOT_CAPITAL_APPROVAL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
