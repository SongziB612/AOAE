"""Two bounded public-source coverage probes; no orders, login, or paid data."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import akshare as ak


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('new workspace directory required')
    output.mkdir(parents=True)
    rows = []
    for period in ('1', '5'):
        row = {'symbol': '510300', 'period_minutes': period,
               'requested_start': '2022-01-01 09:30:00', 'adjustment': 'raw',
               'captured_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            frame = ak.fund_etf_hist_min_em(symbol='510300', period=period, adjust='',
                    start_date=row['requested_start'], end_date='2026-09-13 23:59:59')
            row['rows'] = len(frame)
            row['columns'] = list(frame.columns)
            if len(frame):
                path = output / ('510300-' + period + 'min.csv')
                frame.to_csv(path, index=False, encoding='utf-8')
                row.update(first_timestamp=str(frame.iloc[0, 0]), last_timestamp=str(frame.iloc[-1, 0]),
                           sha256=sha256(path.read_bytes()).hexdigest(), status='RECEIVED_UNREVIEWED')
            else:
                row['status'] = 'EMPTY'
        except Exception as exc:
            # Do not log network URLs, headers, or credential-shaped exception text.
            row.update(status='FETCH_FAILED', error_type=type(exc).__name__)
        rows.append(row)
        print(period, row['status'], row.get('rows'), flush=True)
    record = {'provider': 'AKShare public Eastmoney ETF minute adapter', 'akshare_version': ak.__version__,
              'probes': rows, 'capital_authorized': False, 'orders_authorized': False,
              'limits': 'Coverage probe of one instrument, not a complete universe or point-in-time execution dataset; received prices are not observed fills.'}
    with (output/'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
