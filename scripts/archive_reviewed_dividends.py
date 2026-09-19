"""Archive public, already-reviewed PDF sources. Never changes PIT admission."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review = json.loads(args.review.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for i, event in enumerate(review['events']):
        url = event['source_url']
        record = {'symbol': event['symbol'], 'ex_date': event['ex_date'], 'url': url,
                  'requested_at_utc': datetime.now(timezone.utc).isoformat()}
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('www.sse.com.cn', 'www.nffund.com'):
            raise ValueError('source outside reviewed public hosts')
        if not parsed.path.lower().endswith('.pdf'):
            record['status'] = 'SKIPPED_NON_PDF'
        else:
            try:
                response = requests.get(url, timeout=30, allow_redirects=False)
                record.update({'http_status': response.status_code,
                               'content_type': response.headers.get('Content-Type'),
                               'received_at_utc': datetime.now(timezone.utc).isoformat()})
                response.raise_for_status()
                if response.status_code != 200 or not response.content.startswith(b'%PDF-'):
                    raise ValueError('response is not a PDF document')
                name = f'{i:02d}-{event["symbol"]}-{event["ex_date"]}.pdf'
                with (args.output / name).open('xb') as stream:
                    stream.write(response.content)
                record.update({'status': 'ARCHIVED', 'file': name,
                               'bytes': len(response.content), 'sha256': sha256(response.content).hexdigest()})
            except (requests.RequestException, ValueError) as error:
                record.update({'status': 'FAILED', 'error_type': type(error).__name__})
        records.append(record)
        print(json.dumps(record), flush=True)
    manifest = {'review_path': str(args.review), 'review_sha256': sha256(args.review.read_bytes()).hexdigest(),
                'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                'records': records, 'point_in_time_admitted': False,
                'limit': 'Present-day archive does not establish historical capture or first availability; PDF signature is not semantic verification.'}
    with (args.output / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
