from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import akshare as ak
import pandas as pd
from aoae.daily_snapshot import validate_daily_frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--overlap-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest.exists():
        raise FileExistsError(f'refusing to overwrite manifest: {args.manifest}')
    if len(args.symbols) != len(set(args.symbols)):
        raise ValueError('duplicate requested symbols')
    if args.output_dir.exists() and any(args.output_dir.glob("*.csv")):
        raise FileExistsError(f"refusing to overwrite daily prices: {args.output_dir}")
    start, end = pd.Timestamp(args.overlap_date), pd.Timestamp(args.end_date)
    if end < start:
        raise ValueError("end date precedes overlap date")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for symbol in args.symbols:
        started_at = datetime.now(timezone.utc).isoformat()
        prefix = "sz" if symbol.startswith(("15", "16")) else "sh"
        frame = ak.fund_etf_hist_sina(symbol=prefix + symbol)
        received_at = datetime.now(timezone.utc).isoformat()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.loc[(frame["date"] >= start) & (frame["date"] <= end), ["date", "open", "high", "low", "close", "volume", "amount"]]
        frame = validate_daily_frame(frame, start, end)
        payload = frame.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
        (args.output_dir / f"{symbol}.csv").write_bytes(payload)
        records[symbol] = {
            "request_started_at_utc": started_at, "response_received_at_utc": received_at,
            "rows": len(frame), "first_date": frame.iloc[0]["date"].date().isoformat(),
            "last_market_date": frame.iloc[-1]["date"].date().isoformat(), "sha256": sha256(payload).hexdigest(),
        }
    latest_dates = {record["last_market_date"] for record in records.values()}
    if len(latest_dates) != 1:
        raise ValueError(f"incomplete cross-asset close: latest dates differ: {records}")
    manifest = {
        "schema_version": 1, "provider": "Sina via AKShare fund_etf_hist_sina",
        "adapter_version": ak.__version__, "requested_end_date": end.date().isoformat(), "files": records,
        "timing_limit": "Local request/receipt times are not vendor publication or historical first-availability times.",
        "orders_authorized": False, "capital_authorized": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
