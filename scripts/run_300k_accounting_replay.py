"""Raw-price/event-assumption replay across monthly twelve-month starts."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
import re
from pathlib import Path

import pandas as pd

from aoae.corporate_action_replay import infer_actions, replay, total_return_signals
from aoae.etf_momentum import load_prices, load_spec, metrics
from aoae.etf_risk_overlay import build_overlay_schedule


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--distribution-manifest', type=Path)
    parser.add_argument('--split-corrections', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec_path = Path('research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
    spec = load_spec(spec_path)
    opens, closes, hashes = load_prices(args.data_dir, spec.symbols)
    manifest_path = args.data_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    actions, price_audit = [], []
    for record in manifest['records']:
        s = record['symbol']
        if record.get('errors') or hashes[s] != record['sources']['prices']['csv_sha256']:
            raise ValueError('capture errors or CSV hash mismatch')
        factor_source = record['sources']['factors']
        payload = Path(factor_source['path']).read_bytes()
        if sha256(payload).hexdigest() != factor_source['sha256']:
            raise ValueError('factor hash mismatch')
        factors, _ = json.JSONDecoder().raw_decode(payload.decode('utf-8').split('=', 1)[1].strip())
        if factors != factor_source['decoded']:
            raise ValueError('decoded factor mismatch')
        actions.extend(infer_actions(s, factors['data']))
        qfq = pd.read_csv(Path('data/raw/cn_etf') / f'{s}.csv', parse_dates=['date']).set_index('date')
        overlap = qfq.index.intersection(closes.index)
        difference = qfq.loc[overlap, 'close'] - closes.loc[overlap, s]
        price_audit.append({'symbol': s, 'overlap_days': len(overlap),
                            'days_different_close_above_0_001': int((difference.abs() > .001000001).sum()),
                            'largest_absolute_close_difference': round(float(difference.abs().max()), 6)})
    distribution_audit = []
    if args.distribution_manifest:
        distributions = json.loads(args.distribution_manifest.read_text(encoding='utf-8'))
        payment_map, table_cash_events = {}, set()
        for record in distributions['records']:
            if record.get('error'):
                raise ValueError('distribution capture failure')
            html = args.distribution_manifest.parent / (record['symbol'] + '.html')
            if sha256(html.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError('distribution HTML hash mismatch')
            for table in record['tables']:
                if '除息日' not in table['columns']:
                    continue
                for row in table['rows']:
                    if '暂无' in row[0]:
                        continue
                    values = dict(zip(table['columns'], row))
                    date = pd.Timestamp(values['除息日'])
                    if date < closes.index[0] or date > closes.index[-1]:
                        continue
                    match = re.fullmatch(r'每10份派现金([0-9.]+)元', values['每10份分红'])
                    if not match:
                        raise ValueError('unknown distribution unit')
                    key = record['symbol'], date
                    if key in payment_map:
                        raise ValueError('duplicate distribution')
                    payment_map[key] = (float(match[1]) / 10, pd.Timestamp(values['分红发放日']))
                    table_cash_events.add(key)
        factor_cash_events = {(a.symbol, a.date) for a in actions if a.cash_per_old_share > 0 and closes.index[0] <= a.date <= closes.index[-1]}
        if factor_cash_events != table_cash_events:
            raise ValueError('cash event coverage differs across providers')
        updated = []
        for action in actions:
            key = action.symbol, action.date
            if key in payment_map:
                amount, payment_date = payment_map[key]
                if abs(amount - action.cash_per_old_share) > 1e-8:
                    raise ValueError('cash amount differs across providers')
                action = replace(action, payment_date=payment_date)
                distribution_audit.append({'symbol': action.symbol, 'ex_date': str(action.date.date()), 'payment_date': str(payment_date.date()), 'cash_per_share': amount})
            updated.append(action)
        actions = updated
    if args.split_corrections:
        corrections = json.loads(args.split_corrections.read_text(encoding='utf-8'))
        for correction in corrections['events']:
            matches = [i for i, a in enumerate(actions) if a.symbol == correction['symbol'] and str(a.date.date()) == correction['provider_factor_date']]
            if len(matches) != 1:
                raise ValueError('split correction must match exactly one event')
            i = matches[0]
            if abs(actions[i].ratio - correction['ratio']) > 1e-8:
                raise ValueError('split ratio differs from primary document')
            actions[i] = replace(actions[i], date=pd.Timestamp(correction['first_post_split_trading_date']), rounding=correction['rounding'])
    signals = total_return_signals(closes, actions)
    schedule = build_overlay_schedule(signals, spec, 63, .12)
    starts = pd.date_range('2022-01-01', '2025-09-01', freq='MS')
    rows = []
    for start in starts:
        end = start + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        for lag in ((0,) if args.distribution_manifest else (0, 5, 10)):
            for slip in (0, 30, 100):
                eq, orders, state = replay(opens, closes, schedule, actions, spec.risk_assets,
                                           str(start.date()), str(end.date()),
                                           slippage_bps=slip, pay_lag_sessions=lag, use_payment_dates=bool(args.distribution_manifest))
                row = {'start': str(start.date()), 'end': str(end.date()),
                       'assumed_payment_lag_sessions': lag, 'slippage_bps': slip,
                       'net_pnl_cny': round(float(eq.iloc[-1]) - 300000., 2),
                       'maximum_loss_from_initial_cny': round(max(0., 300000. - float(eq.min())), 2),
                       'metrics': metrics(eq, 300000., str(start.date())),
                       'order_count': len(orders), 'state': state}
                rows.append(row)
    groups = []
    for lag in ((0,) if args.distribution_manifest else (0, 5, 10)):
        for slip in (0, 30, 100):
            selected = [r for r in rows if r['assumed_payment_lag_sessions'] == lag and r['slippage_bps'] == slip]
            worst, best = min(selected, key=lambda r: r['net_pnl_cny']), max(selected, key=lambda r: r['net_pnl_cny'])
            groups.append({'assumed_payment_lag_sessions': lag, 'slippage_bps': slip,
                           'overlapping_windows': len(selected),
                           'worst_pnl_cny': worst['net_pnl_cny'], 'worst_start': worst['start'],
                           'best_pnl_cny': best['net_pnl_cny'], 'best_start': best['start'],
                           'median_pnl_cny': float(pd.Series([r['net_pnl_cny'] for r in selected]).median()),
                           'losing_windows': sum(r['net_pnl_cny'] < 0 for r in selected),
                           'paused_windows': sum(r['state']['paused'] for r in selected)})
    benchmark_rows = []
    for start in starts:
        end = start + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        first = closes.index[closes.index >= start][0]
        previous = closes.index[closes.index.get_loc(first) - 1]
        simple_schedule = {first: ({spec.benchmark: 1.}, {}, str(previous.date()), {})}
        eq, _, state = replay(opens, closes, simple_schedule, actions, spec.risk_assets,
                               str(start.date()), str(end.date()), slippage_bps=30, pay_lag_sessions=5, use_payment_dates=bool(args.distribution_manifest))
        benchmark_rows.append({'start': str(start.date()), 'net_pnl_cny': round(float(eq.iloc[-1]) - 300000., 2), 'paused': state['paused']})
    matched = [r for r in rows if r['assumed_payment_lag_sessions'] == (0 if args.distribution_manifest else 5) and r['slippage_bps'] == 30]
    beat = sum(r['net_pnl_cny'] > b['net_pnl_cny'] for r, b in zip(matched, benchmark_rows))
    source_paths = [Path(__file__), Path('src/aoae/corporate_action_replay.py'), Path('src/aoae/etf_risk_overlay.py'), Path('src/aoae/etf_momentum.py'), Path('src/aoae/small_account.py'), spec_path, manifest_path]
    if args.distribution_manifest:
        source_paths.append(args.distribution_manifest)
    if args.split_corrections:
        source_paths.append(args.split_corrections)
    result = {
        'status': 'RESEARCH_ONLY_UNVERIFIED_CORPORATE_ACTION_ASSUMPTIONS',
        'initial_capital_cny': 300000, 'pause_loss_cny': 100000,
        'commission_rate_each_side': .003, 'minimum_commission_cny': 5,
        'method': 'Causal total-return signal index; raw prior-close sized targets; raw next-open simulated fills; cash receivables; next-open loss pause liquidation.',
        'input_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in source_paths},
        'price_sha256': hashes,
        'price_audit': price_audit,
        'payment_date_mode': 'cross_provider_published_dates' if args.distribution_manifest else 'assumed_session_lag',
        'cross_provider_cash_event_audit': distribution_audit,
        'inferred_actions': [{**asdict(a), 'date': str(a.date.date()), 'payment_date': str(a.payment_date.date()) if a.payment_date is not None else None} for a in actions],
        'scenario_count': len(rows), 'summary': groups, 'windows': rows,
        'benchmark_windows': benchmark_rows,
        'strategy_beats_simple_benchmark_windows_at_selected_payment_mode_30bps': beat,
        'interpretation_limits': [
            'Split interpretation, completeness and share rounding still require primary-document reconciliation.',
            ('Cash amounts and ex-dates agree across two providers; payment dates come from the distribution table and are not verified broker settlements.' if args.distribution_manifest else 'Payment delays 0/5/10 sessions are assumptions, not actual dates or proven bounds.'),
            'Changing from QFQ signals to a causal total-return index changes strategy outputs; this is a challenger, not the frozen pilot.',
            'Scenarios reuse 45 overlapping windows: neither independent trials nor a probability of future profit.',
            'No full depth, partial fill, settlement restriction, suspension, limit price or order submission latency model.',
            'Uses intersection calendar; symbol-specific nontrading dates may be omitted.',
            'Commission is a scenario, not confirmed personal pricing; no terminal liquidation cost.',
            'Stop is evaluated at observed close, cannot cap overnight or intraday loss.',
            'Independent implementation review and untouched prospective validation remain outstanding.'
        ],
        'capital_authorized': False, 'orders_authorized': False, 'broker_connection_authorized': False
    }
    if args.distribution_manifest:
        for row in rows + groups:
            row['assumed_payment_lag_sessions'] = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'scenario_count': len(rows), 'summary': groups, 'price_audit': price_audit, 'benchmark_beaten_windows': beat}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
