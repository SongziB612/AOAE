"""Finite-year exchange session planning; never infer future-year holidays."""
from datetime import date, datetime, timedelta, timezone


def latest_closed_session(config, at):
    """Choose capture date using Shanghai close, including weekend recovery.

    This is an observation-date selector, never a simulated decision clock.
    Unknown years and a missing prior session fail closed.
    """
    now = datetime.fromisoformat(at)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware timestamp required')
    local = now.astimezone(timezone(timedelta(hours=8)))
    if local.year != config['year']:
        raise ValueError('calendar year not reviewed')
    today = local.date().isoformat()
    closed = [d for d in sessions(config) if d < today or (d == today and local.hour >= 15)]
    if not closed:
        raise ValueError('no reviewed closed session')
    return closed[-1]


def sessions(config):
    year = config['year']
    if type(year) is not int or config.get('weekend_closed') is not True:
        raise ValueError('unsupported calendar')
    holidays = set()
    for first, last in config['holiday_ranges']:
        begin, end = date.fromisoformat(first), date.fromisoformat(last)
        if begin.year != year or end.year != year or begin > end:
            raise ValueError('invalid holiday range')
        while begin <= end:
            holidays.add(begin)
            begin += timedelta(days=1)
    day, end = date(year, 1, 1), date(year, 12, 31)
    result = []
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def day_plan(config, value):
    day = date.fromisoformat(value)
    if day.year != config['year']:
        raise ValueError('calendar year not reviewed')
    days = sessions(config)
    future = [d for d in days if d > value]
    following = future[0] if future else None
    trading = value in days
    month_end = trading and (following is None or following[:7] != value[:7])
    return {'is_session': trading, 'next_session': following, 'is_month_end': month_end,
            'signal_schedule': 'MARKET_CLOSED' if not trading else 'NEXT_SESSION_UNREVIEWED' if following is None else 'MONTH_END_SIGNAL_DUE' if month_end else 'NOT_A_SIGNAL_DAY',
            'instrument_suspensions_verified': False}
