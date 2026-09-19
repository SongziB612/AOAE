"""Descriptive scale audit, not a new independent strategy trial or live gate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.small_account import simulate_small_account, executable_benchmark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec_path = Path('research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
    admission_path = Path('research/data_admissions/0004-cn-etf-history/result.json')
    objective_path = Path('research/capital_readiness/user-objective-2026-09-05.json')
    objective = json.loads(objective_path.read_text(encoding='utf-8'))
    capital = float(objective['initial_capital_cny'])
    limit = float(objective['stated_loss_tolerance_cny'])
    spec = load_spec(spec_path)
    opens, closes, hashes = load_prices(Path('data/raw/cn_etf'), spec.symbols)
    admission = json.loads(admission_path.read_text(encoding='utf-8'))
    if any(hashes[s] != admission['files'][s]['sha256'] for s in spec.symbols):
        raise ValueError('Frozen price hashes differ from admission')
    periods = [('2022-01-01', '2026-08-31')]
    periods += [(f'{year}-01-01', f'{year}-12-31') for year in range(2022, 2026)]
    rows = []
    for start, end in periods:
        for slip in (0, 30, 100):
            equity, trades, diagnostics = simulate_small_account(
                opens, closes, spec, start, end, capital,
                1.0, 100, 0.003, 5., 63, 0.12, slip)
            result = metrics(equity, capital, start)
            peaks = equity.cummax().clip(lower=capital)
            # Independent arithmetic check of the reported drawdown.
            expected_dd = min(float(v / p - 1) for v, p in zip(equity, peaks))
            assert abs(result['max_drawdown'] - expected_dd) < 1e-7
            rows.append({
                'period': [start, end], 'starts_in_cash': True,
                'slippage_bps_each_side': slip, 'metrics': result,
                'ending_equity_cny': round(float(equity.iloc[-1]), 2),
                'net_pnl_cny': round(float(equity.iloc[-1]) - capital, 2),
                'maximum_loss_from_initial_cny': round(max(0., capital - float(equity.min())), 2),
                'maximum_peak_to_trough_loss_cny': round(float((peaks - equity).max()), 2),
                'loss_tolerance_breached_at_observed_close': bool((equity < capital - limit).any()),
                'costs_cny': round(sum(t['cost_cny'] for t in trades), 2),
                'orders': sum(len(t['legs']) for t in trades),
                'diagnostics': diagnostics,
            })
    benchmark = executable_benchmark(opens, closes, spec.benchmark, *periods[0], capital, 100, 0.003, 5.)
    files = [spec_path, admission_path, objective_path, Path(__file__),
             Path('src/aoae/etf_momentum.py'), Path('src/aoae/small_account.py'),
             Path('src/aoae/etf_risk_overlay.py')]
    record = {
        'record_type': 'post_discovery_300000_cny_scale_diagnostic',
        'status': 'NOT_ADMISSIBLE_FOR_CAPITAL',
        'initial_capital_cny': capital,
        'price_adjustment': admission['adjustment'],
        'input_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in files},
        'price_sha256': hashes, 'scenarios': rows,
        'buy_hold_benchmark_no_extra_slippage': metrics(benchmark, capital, periods[0][0]),
        'cash_benchmark_net_return_assuming_zero_interest': 0.,
        'limitations': [
            'QFQ adjusted prices used as executable prices: no verified raw-price/corporate-action ledger.',
            'Existing reused historical data, no clean independent holdout and no future return forecast.',
            'No order-book depth, participation cap, partial fill or suspension simulation.',
            'Order sizing uses realized opening prices: not proof of pre-open executable orders.',
            'No operational loss stop simulated; daily closes can miss larger intraday losses.',
            'Calendar-year fresh-cash runs are not all rolling twelve-month starting dates.',
            'Cost rate 0.003 is a conservative scenario, not verified personal broker pricing.',
            'Slippage charged as additive cash cost; no terminal liquidation cost.',
            'Independent arithmetic check is not independent economic validation.'
        ],
        'first_principles_review': {
            'economic_hypothesis': 'Trend persistence; compensation may be exposure to market risk rather than alpha.',
            'identified_structural_payer': None,
            'risk_of_ruin_established': False,
            'decision': 'Audit corporate actions and execution before interpreting scale results as investable.'
        },
        'capital_authorized': False, 'orders_authorized': False,
        'broker_connection_authorized': False
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': record['status'], 'scenarios': rows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
