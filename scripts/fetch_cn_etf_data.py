from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import akshare as ak
import pandas as pd


COLUMNS = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if args.output_dir.exists() and any(args.output_dir.glob("*.csv")):
        raise FileExistsError(f"refusing to overwrite existing ETF snapshots: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for symbol in spec["data"]["universe"]:
        frame = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=spec["data"]["start_date"].replace("-", ""), end_date=spec["data"]["end_date"].replace("-", ""), adjust=spec["data"]["adjustment"])
        missing = set(COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(f"{symbol} missing source columns: {sorted(missing)}")
        frame = frame.rename(columns=COLUMNS)[list(COLUMNS.values())]
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date")
        if frame.empty or frame["date"].duplicated().any() or frame.isna().any().any() or (frame[["open", "close", "high", "low"]] <= 0).any().any():
            raise ValueError(f"{symbol} failed data audit")
        payload = frame.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
        path = args.output_dir / f"{symbol}.csv"
        path.write_bytes(payload)
        records[symbol] = {"rows": len(frame), "first_date": frame.iloc[0]["date"].date().isoformat(), "last_date": frame.iloc[-1]["date"].date().isoformat(), "sha256": sha256(payload).hexdigest()}
        print(f"{symbol}: {len(frame)} rows {records[symbol]['first_date']}..{records[symbol]['last_date']}")
    manifest = {"schema_version": 1, "provider": spec["data"]["provider"], "adapter_version": ak.__version__, "adjustment": spec["data"]["adjustment"], "files": records, "checks": {"all_symbols_present": set(records) == set(spec["data"]["universe"]), "dates_unique": True, "required_values_positive": True}, "redistribution_authorized": False}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
