"""Bounded public capture, durable failure logs, cash-only checkpoint."""
import argparse
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from hashlib import sha256
from uuid import uuid4
from aoae.capture_retry import capture_with_retry
from aoae.exchange_calendar import day_plan, latest_closed_session

SYMBOLS = ('510300', '510500', '159915', '513500', '518880', '511010')


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def execute(root, directory, name, command, timeout):
    outcome = {'stage': name, 'started_at_utc': datetime.now(timezone.utc).isoformat()}
    try:
        result = subprocess.run([sys.executable, *command], cwd=root, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        outcome['returncode'] = result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or '', exc.stderr or ''
        outcome.update(returncode=None, error='TIMEOUT')
    for label, content in [('stdout', stdout), ('stderr', stderr)]:
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        with (directory / (name + '.' + label + '.log')).open('x', encoding='utf-8') as stream:
            stream.write(content)
    outcome['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    save(directory / (name + '.result.json'), outcome)
    return outcome


def inspect_snapshot(directory, expected):
    latest = {}
    for symbol in SYMBOLS:
        path = directory / 'prices' / (symbol + '.csv')
        if path.exists():
            with path.open(encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            if rows:
                latest[symbol] = rows[-1]['date']
    ready = len(latest) == len(SYMBOLS) and set(latest.values()) == {expected} and (directory / 'manifest.json').is_file()
    return {'status': 'CURRENT_COMPLETE' if ready else 'INCOMPLETE_OR_STALE', 'latest_market_dates': latest}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--as-of', help='Explicit capture date; default is latest closed Shanghai session.')
    p.add_argument('--attempts', type=int, default=3)
    p.add_argument('--delay-seconds', type=int, default=10)
    args = p.parse_args()
    if args.as_of:
        date.fromisoformat(args.as_of)
    if not 1 <= args.attempts <= 3 or not 0 <= args.delay_seconds <= 30:
        p.error('attempts 1..3; delay 0..30')
    root = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8]
    run = root / 'data/runtime/paired_forward' / run_id
    run.mkdir(parents=True, exist_ok=False)
    summary = {'as_of': args.as_of, 'run_directory': str(run), 'capital_authorized': False,
               'orders_authorized': False, 'scope': 'PUBLIC_CAPTURE_AND_CASH_CHECKPOINT_ONLY'}
    try:
        calendar_path = root / 'configs/cn_exchange_calendar_2026.json'
        calendar_bytes = calendar_path.read_bytes()
        calendar = json.loads(calendar_bytes)
        selected_at = datetime.now(timezone.utc).isoformat()
        latest_closed = latest_closed_session(calendar, selected_at)
        summary['date_selection'] = 'EXPLICIT' if args.as_of else 'LATEST_CLOSED_SESSION'
        args.as_of = args.as_of or latest_closed
        summary['as_of'] = args.as_of
        summary['date_selected_at_utc'] = selected_at
        if args.as_of > latest_closed:
            raise ValueError('requested date is not yet a closed session')
        summary['calendar_sha256'] = sha256(calendar_bytes).hexdigest()
        summary['calendar_plan'] = day_plan(json.loads(calendar_bytes), args.as_of)
        summary['strategy_status'] = 'REVIEWED_INPUT_DISPATCH_NOT_YET_RUN'
        if not summary['calendar_plan']['is_session']:
            summary['status'] = 'SKIP_MARKET_CLOSED_NO_LEDGER_ADVANCE'
            return 0
        def attempt(number):
            directory = run / ('attempt-' + str(number))
            directory.mkdir()
            result = execute(root, directory, 'fetch', ['scripts/fetch_sina_daily_prices.py', '--symbols', *SYMBOLS,
                '--overlap-date', '2026-08-31', '--end-date', args.as_of, '--output-dir', str(directory / 'prices'),
                '--manifest', str(directory / 'manifest.json')], 90)
            snapshot = inspect_snapshot(directory, args.as_of)
            if result['returncode'] != 0:
                snapshot['status'] = 'FETCH_FAILED'
            snapshot.update(directory=str(directory), fetch=result)
            save(directory / 'snapshot-status.json', snapshot)
            print(json.dumps({'attempt': number, **snapshot}), flush=True)
            return snapshot
        captured = capture_with_retry(attempt, args.attempts, args.delay_seconds)
        summary.update(captured)
        if captured['status'] != 'CAPTURE_READY':
            summary['failure_reason'] = ('SOURCE_DATA_NOT_CURRENT' if all(
                a['status'] == 'INCOMPLETE_OR_STALE' for a in captured['attempts']) else 'FETCH_OR_DATA_FAILURE')
            summary['recovery_policy'] = 'Next scheduled invocation retries the latest closed session; no fabricated timestamps or fills.'
            return 1
        directory = Path(captured['attempts'][-1]['directory'])
        collector = execute(root, directory, 'collect', ['scripts/collect_paired_forward.py',
            '--manifest', str(directory / 'manifest.json'), '--data-dir', str(directory / 'prices'),
            '--expected-market-date', args.as_of, '--output-dir', str(directory / 'records')], 60)
        summary['collector'] = collector
        if collector['returncode'] != 0:
            summary['status'] = 'COLLECTOR_FAILED_NO_LEDGER_ADVANCE'
            return 1
        records = list((directory / 'records').glob('*.json'))
        if len(records) != 1:
            raise ValueError('expected exactly one captured record')
        ledger = execute(root, directory, 'checkpoint', ['scripts/run_paired_cash_checkpoint.py',
            '--record', str(records[0]), '--manifest', str(directory / 'manifest.json'),
            '--data-dir', str(directory / 'prices'), '--database', str(root / 'data/runtime/paired_forward/cash-journal.sqlite3')], 60)
        summary['checkpoint'] = ledger
        summary['status'] = 'CASH_CHECKPOINT_PASS' if ledger['returncode'] == 0 else 'CHECKPOINT_FAILED_REVIEW_REQUIRED'
        if ledger['returncode'] != 0:
            return 1
        strategy = execute(root, directory, 'strategy', ['scripts/run_paired_strategy_cycle.py',
            '--as-of', args.as_of, '--output', str(directory / 'strategy-status.json')], 60)
        summary['strategy'] = strategy
        summary['scope'] = 'PUBLIC_CAPTURE_CASH_CHECKPOINT_AND_REVIEWED_SHADOW_DISPATCH'
        summary['strategy_status'] = 'DISPATCH_PASS_NOT_CAPITAL_APPROVAL' if strategy['returncode'] == 0 else 'BLOCKED_REVIEW_REQUIRED'
        summary['status'] = 'PAIRED_WORKFLOW_PASS_NOT_CAPITAL_APPROVAL' if strategy['returncode'] == 0 else 'STRATEGY_BLOCKED_REVIEW_REQUIRED'
        return 0 if strategy['returncode'] == 0 else 1
    except Exception as exc:
        summary.update(status='CYCLE_ERROR_REVIEW_REQUIRED', error=type(exc).__name__ + ': ' + str(exc))
        return 1
    finally:
        save(run / 'cycle-status.json', summary)
        print(json.dumps({'status': summary.get('status'), 'report': str(run / 'cycle-status.json')}), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
