"""Reviewed-input dispatch and paired reporting; no broker adapter or approvals."""
from decimal import Decimal
import json

from aoae.etf_momentum import load_spec
from aoae.exchange_calendar import day_plan, sessions
from aoae.reviewed_day import build_day
from aoae.reviewed_signal import build_event


def comparison(state):
    accounts = state['accounts']
    rows = {arm: {'equity_cny': a['equity'],
                  'net_pnl_cny': str(Decimal(a['equity']) - Decimal(a['initial'])),
                  'modeled_cost_cny': a['cost'], 'max_drawdown': a['max_drawdown'],
                  'modeled_fills': a['fills'], 'paused': a['paused']}
            for arm, a in accounts.items()}
    model = 'causal_total_return_momentum_overlay'
    excess = {arm: str(Decimal(accounts[model]['equity']) - Decimal(a['equity']))
              for arm, a in accounts.items() if arm != model} if model in accounts else {}
    monthly = []
    prior = {arm: Decimal(a['initial']) for arm, a in accounts.items()}
    for entry in state['daily']:
        month = entry['day'][:7]
        if not monthly or monthly[-1]['month'] != month:
            monthly.append({'month': month, 'opening_equity_cny': {a: str(v) for a, v in prior.items()},
                            'last_modeled_day': None, 'modeled_observations': 0})
        row = monthly[-1]
        row.update(last_modeled_day=entry['day'], closing_equity_cny=entry['equity'])
        row['modeled_observations'] += 1
        row['net_change_cny'] = {a: str(Decimal(v) - Decimal(row['opening_equity_cny'][a]))
                                 for a, v in entry['equity'].items()}
        row['complete_calendar_month_verified'] = False
        prior = {a: Decimal(v) for a, v in entry['equity'].items()}
    return {'arms': rows, 'model_minus_baseline_cny': excess,
            'monthly_marked_comparisons': monthly,
            'saved_signals': len(state['signals']), 'modeled_days': len(state['daily']),
            'observed_broker_fills': 0, 'realized_real_money_profit_cny': '0',
            'valuation_note': 'Marked NAV after modeled costs; not liquidation proceeds or observed fills.',
            'first_principles_challenge': {
                'economic_payer': 'Underlying ETF market exposure; incremental timing edge remains unproven.',
                'net_executable_value': 'UNKNOWN: modeled costs do not establish executable fills.',
                'risk_of_ruin': 'NOT_ESTIMATED: pause threshold is not a guaranteed loss bound.',
                'complexity_admission': 'No capital pass without independent net improvement over simple baselines.'},
            'profitability_established': False, 'capital_authorized': False}


def run_workflow(root, day, calendar, journal, freeze, now):
    plan = day_plan(calendar, day)
    result = {'day': day, 'plan': plan, 'stages': [], 'blockers': [],
              'capital_authorized': False, 'orders_authorized': False}
    state = journal.audit()['state']
    if state is None or state['freeze'] != freeze:
        raise ValueError('missing or mismatched shadow genesis')
    try:
        if not plan['is_session']:
            result['stages'].append('MARKET_CLOSED')
            return result
        inbox = root / 'research/reviewed_inputs' / day
        daily_path = inbox / 'day-bundle.json'
        # Never count idle cash observations as strategy evaluation days.
        pending_from_prior_day = state['pending_signal'] and state['signals'][-1]['day'] < day
        needs_day = bool(state['daily'] or pending_from_prior_day or any(
            any(a['positions'].values()) or a['receivables'] for a in state['accounts'].values()))
        if daily_path.exists():
            bundle = json.loads(daily_path.read_text(encoding='utf-8'))
            if bundle['day'] != day:
                raise ValueError('wrong day bundle')
            spec = load_spec(root / 'research/hypotheses/0004-cn-etf-dual-momentum/spec.json')
            event = build_day(root, bundle, spec.risk_assets, now)
            reviewed_sessions = sessions(calendar)
            i = reviewed_sessions.index(day)
            if i == 0 or event['previous_day'] != reviewed_sessions[i - 1]:
                raise ValueError('reviewed calendar disagrees with scheduler')
            appended = journal.append('MODELED_DAY:' + day, event)
            result['stages'].append('DAY_APPENDED' if appended else 'DAY_ALREADY_RECORDED')
            state = journal.audit()['state']
        elif needs_day:
            result['blockers'].append('MISSING_REVIEWED_DAY_BUNDLE: ' + str(daily_path))
        else:
            result['stages'].append('IDLE_CASH_NOT_A_STRATEGY_EVALUATION_DAY')
        if plan['is_month_end']:
            signal_path = inbox / 'signal-bundle.json'
            if result['blockers']:
                result['blockers'].append('SIGNAL_BLOCKED_BY_UNVALUED_ACCOUNT')
            elif not signal_path.exists():
                result['blockers'].append('MISSING_REVIEWED_SIGNAL_BUNDLE: ' + str(signal_path))
            else:
                bundle = json.loads(signal_path.read_text(encoding='utf-8'))
                if bundle['signal_day'] != day:
                    raise ValueError('wrong signal bundle')
                event = build_event(root, bundle, freeze, now)
                if event['review']['next_session'] != plan['next_session']:
                    raise ValueError('signal calendar disagrees with scheduler')
                appended = journal.append('PRESAVE_SIGNAL:' + day, event)
                result['stages'].append('SIGNAL_PRESAVED' if appended else 'SIGNAL_ALREADY_RECORDED')
        else:
            result['stages'].append('NOT_A_MONTH_END_SIGNAL_DAY')
    except Exception as exc:
        result['blockers'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        audit = journal.audit()
        result['journal_head_sha256'] = audit['head_sha256']
        result['comparison'] = comparison(audit['state'])
        result['status'] = 'BLOCKED_REVIEW_REQUIRED' if result['blockers'] else 'WORKFLOW_PASS_NOT_CAPITAL_APPROVAL'
        result['pre_capital_unresolved'] = [
            'Complete independently reviewed source bundles and instrument tradability evidence.',
            'Independent forward net economics and measured execution, not modeled fills.',
            'Account-specific fees/permissions and explicit real-capital authorization.']
    return result
