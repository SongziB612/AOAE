"""Future-mutation audit of the actual historical signal/accounting path."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aoae.corporate_action_replay import Action, replay, total_return_signals
from aoae.etf_momentum import load_prices, load_spec
from aoae.etf_risk_overlay import build_overlay_schedule


def main():
    output = Path('research/experiments/causal-history-0001/result-v1.json')
    if output.exists():
        raise FileExistsError(output)
    config_path = Path('research/experiments/cn-fees-0001/config.json')
    c = json.loads(config_path.read_text(encoding='utf-8'))
    ref = json.loads(Path(c['reference']).read_text(encoding='utf-8'))
    spec = load_spec(Path(c['strategy_spec']))
    opens, closes, hashes = load_prices(Path(c['data_dir']), spec.symbols)
    assert hashes == ref['price_sha256'], 'historical data changed'
    actions = [Action(**{**a, 'date': pd.Timestamp(a['date']),
                         'payment_date': pd.Timestamp(a['payment_date']) if a['payment_date'] else None})
               for a in ref['inferred_actions']]

    def schedule(prices, events):
        return build_overlay_schedule(total_return_signals(prices, events), spec,
                                      c['lookback'], c['target_volatility'])

    def account(op, cl, sch, events, year):
        return replay(op, cl, sch, events, spec.risk_assets, f'{year}-01-01', f'{year}-12-31',
                      initial=c['initial_cny'], commission=.0002, slippage_bps=30,
                      pause_loss=c['pause_loss_cny'], use_payment_dates=True)

    baseline = schedule(closes, actions)
    accounts = {year: account(opens, closes, baseline, actions, year) for year in c['years']}
    checks = []
    for execution, original in baseline.items():
        cutoff = pd.Timestamp(original[2])
        if cutoff.year not in c['years']:
            continue
        # Prices and corporate actions after the known information boundary are
        # deliberately unrealistic. This tests dependency, not stress profits.
        mask = closes.index > cutoff
        modified_close, modified_open = closes.copy(), opens.copy()
        multiplier = np.where(np.arange(mask.sum()) % 2, 10., .1)
        modified_close.loc[mask] *= multiplier[:, None]
        modified_open.loc[mask] *= multiplier[::-1, None]
        past_actions = [a for a in actions if a.date <= cutoff]
        altered = schedule(modified_close, past_actions)
        assert altered[execution] == original, 'future data changed prior signal'
        before, orders, _ = accounts[cutoff.year]
        after, altered_orders, _ = account(modified_open, modified_close, altered, past_actions, cutoff.year)
        pd.testing.assert_series_equal(before.loc[:cutoff], after.loc[:cutoff], check_exact=True)
        prior_orders = [o for o in orders if pd.Timestamp(o['date']) <= cutoff]
        assert prior_orders == [o for o in altered_orders if pd.Timestamp(o['date']) <= cutoff]
        assert closes.index[closes.index.get_loc(execution) - 1] == cutoff
        checks.append({'signal_date': str(cutoff.date()), 'execution_date': str(execution.date()),
                       'unchanged_prior_orders': len(prior_orders), 'status': 'PASS'})
    assert len(checks) == 48, f'expected 48 monthly decisions, got {len(checks)}'
    files = [str(config_path), c['reference'], c['strategy_spec'], __file__,
             'src/aoae/corporate_action_replay.py', 'src/aoae/etf_risk_overlay.py',
             'src/aoae/etf_momentum.py', 'src/aoae/small_account.py']
    result = {'status': 'PASS', 'checks': checks, 'price_sha256': hashes,
              'input_sha256': {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},
              'limits': ['Dependency test only, not an independent pricing oracle.',
                         'Does not prove historical source availability, universe selection, or dividend announcements were PIT.',
                         'Does not validate intraday fills, limit orders, full sale availability, or future profitability.'],
              'capital_authorized': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'status': result['status'], 'monthly_checks': len(checks), 'output': str(output)}))


if __name__ == '__main__':
    main()
