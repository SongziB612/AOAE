"""Freeze the current candidate and controls without scheduling or starting trading."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from aoae.research_freeze import verify_freeze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        parser.error('choose exactly one of --output or --verify')
    root = Path(__file__).resolve().parents[1]
    if args.verify:
        result = verify_freeze(root, json.loads(args.verify.read_text(encoding='utf-8')))
        print(json.dumps(result, indent=2))
        return 0 if result['status'] == 'INTACT' else 1
    paths = [
        'src/aoae/corporate_action_replay.py', 'src/aoae/etf_momentum.py',
        'src/aoae/etf_risk_overlay.py', 'src/aoae/small_account.py',
        'src/aoae/independent_cash_ledger.py', 'scripts/challenge_300k_baselines.py',
        'scripts/run_300k_accounting_replay.py',
        'research/hypotheses/0004-cn-etf-dual-momentum/spec.json',
        'research/capital_readiness/first-principles-comparison-spec.json',
        'research/capital_readiness/300k-accounting-replay-v4.json',
        'research/capital_readiness/verified-split-timing-2026-09-05.json'
    ]
    paths += [f'data/audit/etf-accounting-2026-09-05-v4/{s}.csv' for s in ['510300', '510500', '159915', '513500', '518880', '511010']]
    result = {
        'experiment_id': 'PRO-0003-raw-price-300k-paired-forward',
        'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'FROZEN_NOT_SCHEDULED',
        'initial_paper_capital_per_arm_cny': 300000,
        'arms': ['causal_total_return_momentum_overlay', 'monthly_same_universe_equal_weight', 'monthly_same_universe_exposure_matched_equal_weight'],
        'objective': 'Measure paired after-cost incremental economics on new evidence, not maximize historical Sharpe.',
        'historical_data_is_not_forward_evidence': True,
        'signal_rule': 'First verified common month-end after freeze; save timestamped signal and inputs before its execution window.',
        'execution_rule': 'No retrospective next-open fills accepted as observed execution; late signals are missed, not backfilled.',
        'evaluation': 'Monthly paired reports; fixed twelve-month evaluation after first eligible presaved signal; no automatic capital pass based on elapsed time.',
        'risk_pause_loss_cny': 100000,
        'live_loss_limit_guaranteed': False,
        'funds_are_simulated_only': True,
        'observed_forward_signals': 0,
        'observed_forward_fills': 0,
        'missing_operational_capabilities': ['timestamped pre-execution signal collector', 'raw daily update and verified future corporate actions', 'separate comparable three-arm forward ledger', 'measured execution evidence admission'],
        'changes_require_new_experiment_id_and_no_score_splicing': True,
        'input_sha256': {p: sha256((root / p).read_bytes()).hexdigest() for p in paths},
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False
    }
    verify_freeze(root, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'bound_inputs': len(paths), 'forward_signals': 0}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
