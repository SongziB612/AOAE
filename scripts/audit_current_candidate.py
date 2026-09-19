"""Current 300k candidate snapshot. Never reuse the old 3000-CNY sign-off."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from aoae.forward_journal import ForwardJournal
from aoae.research_freeze import verify_freeze
from aoae.shadow_cycle import reduce_shadow


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root) or args.output.exists():
        raise ValueError('use a new workspace output file')
    freeze_path = root / 'research/prospective/0003-raw-price-300k-paired-forward/freeze.json'
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    integrity = verify_freeze(root, freeze)
    cash = ForwardJournal(root / 'data/runtime/paired_forward/cash-journal.sqlite3').audit()
    shadow = ForwardJournal(root / 'data/runtime/paired_forward/engineering-shadow-v1.sqlite3', reducer=reduce_shadow).audit()
    result_path = root / 'research/experiments/cn-shadow-real-replay-0001/result-v1.json'
    history = json.loads(result_path.read_text(encoding='utf-8'))
    bound = {n: sha256((root / n).read_bytes()).hexdigest() == h for n, h in history['source_sha256'].items()}
    latest = sorted((root / 'data/runtime/paired_forward').glob('*/cycle-status.json'), key=lambda p: p.stat().st_mtime)
    capture = json.loads(latest[-1].read_text(encoding='utf-8')) if latest else None
    result = {'candidate': freeze['experiment_id'], 'evaluated_at_utc': datetime.now(timezone.utc).isoformat(),
        'initial_simulated_cny_per_arm': freeze['initial_paper_capital_per_arm_cny'],
        'freeze_integrity': integrity, 'cash_journal': cash, 'engineering_journal': shadow,
        'historical_accounting_status': history['accounting_verification'], 'historical_source_still_matches': bound,
        'latest_capture_cycle': capture, 'decision': 'DO_NOT_FUND', 'all_controllable_preparation_complete': False,
        'internal_incomplete': [
            'Independent source-content review and complete corporate-action/calendar bundle not admitted.',
            'Scheduled reviewed-input dispatcher is connected, but complete real reviewed bundles and invested-path operational acceptance remain pending.',
            'Measured execution admission and monthly paired economic acceptance are not completed.'],
        'external_unresolved': [
            'Actual account-specific ETF fees/permissions are not confirmed in current candidate evidence.',
            'No clean forward profitability evidence; historical reuse is not a substitute.',
            'Fresh funding decision, amount, loss tolerance and capital ownership need confirmation before any real order.'],
        'scope_note': 'Old 3000-CNY pilot preparation sign-off does not cover this candidate.',
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False,
        'evidence_sha256': {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in [freeze_path, result_path, *latest[-1:]]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({'decision': result['decision'], 'cash_date': cash['state']['market_date'],
        'formal_signals': len(shadow['state']['signals']), 'engine_days': len(shadow['state']['daily']),
        'internal_incomplete': result['internal_incomplete']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
