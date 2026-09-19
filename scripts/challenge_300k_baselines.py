"""Paired same-universe first-principles comparison with independent cash checks."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from aoae.corporate_action_replay import Action, replay, total_return_signals
from aoae.etf_momentum import load_prices, load_spec
from aoae.etf_risk_overlay import build_overlay_schedule
from aoae.independent_cash_ledger import verify_ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    contract_path = Path('research/capital_readiness/first-principles-comparison-spec.json')
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    reference_path = Path(contract['reference'])
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    spec_path = Path('research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
    spec = load_spec(spec_path)
    opens, closes, hashes = load_prices(Path('data/audit/etf-accounting-2026-09-05-v4'), spec.symbols)
    if hashes != reference['price_sha256']:
        raise ValueError('price hashes changed')
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']), 'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}) for a in reference['inferred_actions']]
    original = build_overlay_schedule(total_return_signals(closes, actions), spec, 63, .12)
    schedules = {'champion': original}
    for name, matched in [('equal_weight', False), ('exposure_matched_equal_weight', True)]:
        schedules[name] = {
            date: ({s: (sum(weights.get(a, 0.) for a in spec.risk_assets) if matched else 1.) / len(spec.risk_assets) for s in spec.risk_assets}, scores, signal_date, diagnostics)
            for date, (weights, scores, signal_date, diagnostics) in original.items()
        }
    rows = []
    for expected in reference['windows']:
        if expected['slippage_bps'] != 30:
            continue
        values = {}
        for name, schedule in schedules.items():
            eq, orders, state = replay(opens, closes, schedule, actions, spec.risk_assets, expected['start'], expected['end'], use_payment_dates=True)
            dates = [str(d.date()) for d in eq.index]
            daily_prices = {str(d.date()): {s: float(closes.at[d, s]) for s in spec.risk_assets} for d in eq.index}
            independent = verify_ledger(dates, daily_prices, orders, reference['inferred_actions'], 300000, .003, 30)
            if max(abs(a - b) for a, b in zip(eq, independent)) > .00001:
                raise ValueError('independent cash ledger mismatch')
            pnl = float(eq.iloc[-1]) - 300000
            if name == 'champion' and abs(round(pnl, 2) - expected['net_pnl_cny']) > .01:
                raise ValueError('champion failed reproduction')
            exit_cost = sum(max(5., q * float(closes.at[eq.index[-1], s]) * .003) + q * float(closes.at[eq.index[-1], s]) * .003 for s, q in state['ending_positions'].items() if q)
            values[name] = {'net_pnl_after_exit_haircut_cny': round(pnl - exit_cost, 2),
                            'max_drawdown': round(float((eq / eq.cummax().clip(lower=300000) - 1).min()), 8),
                            'orders': len(orders), 'cost_cny': state['cost_cny'], 'paused': state['paused']}
        rows.append({'start': expected['start'], 'end': expected['end'], 'portfolios': values})
    summary = {}
    for name in schedules:
        pnl = pd.Series([r['portfolios'][name]['net_pnl_after_exit_haircut_cny'] for r in rows])
        champion = pd.Series([r['portfolios']['champion']['net_pnl_after_exit_haircut_cny'] for r in rows])
        delta = champion - pnl
        summary[name] = {'median_net_pnl_cny': float(pnl.median()), 'worst_net_pnl_cny': float(pnl.min()),
                         'best_net_pnl_cny': float(pnl.max()), 'losing_windows': int((pnl < 0).sum()),
                         'champion_outperforms_windows': int((delta > .01).sum()),
                         'champion_minus_comparator_median_paired_cny': round(float(delta.median()), 2),
                         'worst_window_max_drawdown': min(r['portfolios'][name]['max_drawdown'] for r in rows)}
    files = [contract_path, reference_path, spec_path, Path(__file__), Path('src/aoae/corporate_action_replay.py'), Path('src/aoae/independent_cash_ledger.py'), Path('src/aoae/etf_risk_overlay.py'), Path('src/aoae/etf_momentum.py'), Path('src/aoae/small_account.py')]
    result = {'status': 'DESCRIPTIVE_ATTRIBUTION_NOT_CAPITAL_EVIDENCE', 'summary': summary, 'overlapping_windows': len(rows),
              'portfolios': rows, 'input_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in files}, 'price_sha256': hashes,
              'interpretation_limits': ['Same data reused; no independent holdout and no probability estimate.', 'Equal weight differs in risk exposure; exposure-matched version inherits timing from champion.', 'Shared strategy engine; independent ledger checks accounting, not selection validity.', 'All earlier corporate-action and unmeasured execution limitations remain.', 'Market exposure is not an identified structural payer; no proven risk of ruin estimate.'],
              'capital_authorized': False, 'orders_authorized': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
