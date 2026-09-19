from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import akshare as ak
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.glob("*.csv")):
        raise FileExistsError(f"refusing to overwrite shadow snapshots: {args.output_dir}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    start, end = pd.Timestamp(spec["signal_date"]), pd.Timestamp(spec["data"]["end_date"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for symbol in spec["data"]["universe"]:
        prefix = "sz" if symbol.startswith(("15", "16")) else "sh"
        frame = ak.fund_etf_hist_sina(symbol=prefix + symbol)
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.loc[(frame["date"] >= start) & (frame["date"] <= end), ["date", "open", "high", "low", "close", "volume", "amount"]]
        if frame.empty or frame["date"].duplicated().any() or frame.isna().any().any():
            raise ValueError(f"invalid Sina snapshot: {symbol}")
        payload = frame.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
        (args.output_dir / f"{symbol}.csv").write_bytes(payload)
        records[symbol] = {
            "rows": len(frame),
            "first_date": frame.iloc[0]["date"].date().isoformat(),
            "last_date": frame.iloc[-1]["date"].date().isoformat(),
            "sha256": sha256(payload).hexdigest(),
        }
        print(symbol, records[symbol])
    manifest = {
        "schema_version": 1,
        "provider": "Sina via AKShare fund_etf_hist_sina",
        "adapter_version": ak.__version__,
        "files": records,
        "orders_authorized": False,
        "capital_authorized": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
