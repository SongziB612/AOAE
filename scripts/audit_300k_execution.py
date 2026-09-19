"""Independent ledger reconciliation and prereported fill sensitivity, not live evidence."""
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
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    reference = json.loads(args.reference.read_text(encoding='utf-8'))
    spec_path = Path('research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
    spec = load_spec(spec_path)
    opens, closes, hashes = load_prices(args.data_dir, spec.symbols)
    if hashes != reference['price_sha256']:
        raise ValueError('reference raw price hashes differ')
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']), 'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None}) for a in reference['inferred_actions']]
    schedule = build_overlay_schedule(total_return_signals(closes, actions), spec, 63, .12)
    rows, traces, largest_error = [], [], 0.
    for expected in reference['windows']:
        slip = expected['slippage_bps']
        for fill in ((1., .5, 0.) if slip == 30 else (1.,)):
            eq, orders, state = replay(opens, closes, schedule, actions, spec.risk_assets,
                                       expected['start'], expected['end'],
                                       use_payment_dates=True, slippage_bps=slip, buy_fill_fraction=fill)
            dates = [str(d.date()) for d in eq.index]
            price_dict = {str(d.date()): {s: float(closes.at[d, s]) for s in spec.risk_assets} for d in eq.index}
            independent = verify_ledger(dates, price_dict, orders, reference['inferred_actions'], 300000, .003, slip)
            error = max(abs(a - b) for a, b in zip(eq, independent))
            largest_error = max(largest_error, error)
            if error > .00001:
                raise ValueError('independent daily cash ledger mismatch')
            for order in orders:
                if order['price'] != float(opens.at[pd.Timestamp(order['date']), order['symbol']]):
                    raise ValueError('recorded execution price differs from raw open')
            pnl = round(float(eq.iloc[-1]) - 300000., 2)
            if fill == 1 and (abs(pnl - expected['net_pnl_cny']) > .01 or len(orders) != expected['order_count']):
                raise ValueError('baseline does not reproduce reference')
            # Valuation haircut at last close, NOT a claim of realizable close fills.
            exit_cost = sum(max(5., count * float(closes.at[eq.index[-1], s]) * .003) + count * float(closes.at[eq.index[-1], s]) * slip / 10000
                            for s, count in state['ending_positions'].items() if count)
            row = {'start': expected['start'], 'end': expected['end'], 'slippage_bps': slip,
                   'buy_fill_fraction': fill, 'unfilled_remainder': 'cancelled; no retry until next scheduled rebalance',
                   'net_pnl_before_exit_cost_cny': pnl,
                   'terminal_exit_cost_haircut_cny': round(exit_cost, 2),
                   'net_pnl_after_exit_cost_haircut_cny': round(pnl - exit_cost, 2),
                   'independent_daily_max_abs_error_cny': error, 'orders': len(orders)}
            rows.append(row)
            traces.append({'scenario': len(rows) - 1, 'orders': orders, 'daily_equity': list(zip(dates, [round(float(v), 8) for v in eq]))})
    summary = []
    for slip, fill in [(0, 1.), (30, 1.), (100, 1.), (30, .5), (30, 0.)]:
        selected = [r for r in rows if r['slippage_bps'] == slip and r['buy_fill_fraction'] == fill]
        values = [r['net_pnl_after_exit_cost_haircut_cny'] for r in selected]
        summary.append({'slippage_bps': slip, 'buy_fill_fraction': fill, 'overlapping_windows': len(values),
                        'worst_pnl_cny': min(values), 'median_pnl_cny': float(pd.Series(values).median()),
                        'best_pnl_cny': max(values), 'losing_windows': sum(v < 0 for v in values)})
    trace_path = args.output.with_suffix('.traces.json')
    if trace_path.exists():
        raise FileExistsError(trace_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open('x', encoding='utf-8') as stream:
        json.dump(traces, stream, allow_nan=False, separators=(',', ':'))
    result = {
        'decision': 'NO_LIVE_PILOT_INSUFFICIENT_EXECUTION_AND_OUT_OF_SAMPLE_EVIDENCE',
        'ledger_audit': 'PASS', 'reference_reproduced_windows': len(reference['windows']),
        'independent_ledger_checked_scenarios': len(rows), 'largest_daily_error_cny': largest_error,
        'summary': summary, 'scenarios': rows,
        'source_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in [args.reference, Path(__file__), spec_path, Path('src/aoae/corporate_action_replay.py'), Path('src/aoae/independent_cash_ledger.py'), Path('src/aoae/etf_risk_overlay.py'), Path('src/aoae/etf_momentum.py'), Path('src/aoae/small_account.py')]},
        'price_sha256': hashes, 'trace_path': str(trace_path), 'trace_sha256': sha256(trace_path.read_bytes()).hexdigest(),
        'limits': [
            'Independent Decimal accounting verifies cash/holdings, not independent signal selection or economic alpha.',
            'Input corporate actions inherited from the reference; ledger reproduction cannot validate missing or incorrect source events.',
            'Buy partial-fill percentages are sensitivity assumptions, not measured fill probabilities; sells still assumed fully filled.',
            'Exit cost is a valuation haircut, not a verified executable liquidation or complete tax model.',
            'Overlapping reused historical windows are not independent out-of-sample evidence.',
            'No measured order-book depth, limit-price queue, stale quote or suspension execution evidence.',
            'A failed investment gate does not prove no future strategy can profit.'
        ],
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False
    }
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ['decision', 'ledger_audit', 'reference_reproduced_windows', 'independent_ledger_checked_scenarios', 'largest_daily_error_cny', 'summary']}, indent=2))


if __name__ == '__main__':
    main()
