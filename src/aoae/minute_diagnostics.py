"""Recent bar coverage and timestamp-price proxies, never execution proof."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def inspect_bars(rows, captured_at):
    captured = datetime.fromisoformat(captured_at)
    if captured.tzinfo is None:
        raise ValueError('aware capture time required')
    grouped, previous = defaultdict(dict), None
    zone = timezone(timedelta(hours=8))
    for row in rows:
        at = datetime.strptime(row['day'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=zone)
        if at > captured or (previous and at <= previous):
            raise ValueError('future/duplicate/unsorted bars')
        prices = {k: Decimal(str(row[k])) for k in ('open', 'high', 'low', 'close')}
        volume = Decimal(str(row['volume']))
        if not all(v.is_finite() and v > 0 for v in prices.values()) or not volume.is_finite() or volume < 0:
            raise ValueError('invalid prices/volume')
        if not prices['low'] <= min(prices['open'], prices['close']) <= max(prices['open'], prices['close']) <= prices['high']:
            raise ValueError('inconsistent OHLC')
        grouped[at.date().isoformat()][at.strftime('%H:%M:%S')] = row
        previous = at
    expected = {f'{m//60:02}:{m%60:02}:00' for m in list(range(571, 691))+list(range(781, 901))}
    days = []
    for day, bars in sorted(grouped.items()):
        anchors = ('09:31:00', '09:32:00', '09:36:00')
        eligible = all(t in bars and Decimal(str(bars[t]['volume'])) > 0 for t in anchors)
        proxies = {}
        if eligible:
            base = Decimal(str(bars[anchors[0]]['close']))
            for offset, label in ((1, anchors[1]), (5, anchors[2])):
                proxies[str(offset)] = str((Decimal(str(bars[label]['close'])) / base - 1)*10000)
        days.append({'day': day, 'bars': len(bars), 'missing_continuous_grid_labels': sorted(expected-set(bars)),
                     'extra_labels': sorted(set(bars)-expected), 'anchor_eligible': eligible,
                     'signed_close_to_close_proxy_bps': proxies,
                     'last_close': str(bars['15:00:00']['close']) if '15:00:00' in bars else None})
    return days
