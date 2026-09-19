from __future__ import annotations

import argparse
import json
from pathlib import Path

import akshare as ak
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite audit: {args.output}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    records = {}
    for symbol in spec["data"]["universe"]:
        prefix = "sz" if symbol.startswith(("15", "16")) else "sh"
        independent = ak.fund_etf_hist_sina(symbol=prefix + symbol)
        independent["date"] = pd.to_datetime(independent["date"])
        independent = independent.set_index("date")
        primary = pd.read_csv(args.data_dir / f"{symbol}.csv", parse_dates=["date"]).set_index("date")
        start, end = pd.Timestamp("2026-07-01"), pd.Timestamp(spec["data"]["end_date"])
        joined = primary.loc[start:end, ["open", "close"]].join(independent.loc[start:end, ["open", "close"]], lsuffix="_primary", rsuffix="_independent", how="inner")
        open_offset = joined["open_primary"] - joined["open_independent"]
        close_offset = joined["close_primary"] - joined["close_independent"]
        within_day_offset_error = float((open_offset - close_offset).abs().max()) if len(joined) else float("inf")
        offset_levels = sorted(set(round(float(x), 6) for x in close_offset))
        end_prices_match = bool(abs(float(joined.iloc[-1]["close_primary"]) - float(joined.iloc[-1]["close_independent"])) < 1e-9)
        adjustment_consistent = within_day_offset_error < 1e-9 and len(offset_levels) <= 3
        records[symbol] = {"overlap_rows": len(joined), "qfq_adjustment_offsets": offset_levels, "maximum_within_day_offset_error": round(within_day_offset_error, 8), "adjustment_consistent": adjustment_consistent, "end_close_matches_independent": end_prices_match}
        print(symbol, records[symbol])
    checks = {"all_symbols_have_40_day_overlap": all(x["overlap_rows"] >= 40 for x in records.values()), "all_adjustments_are_piecewise_consistent": all(x["adjustment_consistent"] for x in records.values()), "all_end_closes_match_independent": all(x["end_close_matches_independent"] for x in records.values())}
    output = {"schema_version": 1, "audit_type": "cross_provider_recent_price_check", "primary": "Eastmoney qfq snapshot via fund_etf_hist_em", "independent": "Sina unadjusted via fund_etf_hist_sina", "note": "QFQ and raw prices may differ by a piecewise-constant cash-distribution offset; intraday offsets and end-date closes are checked.", "window": {"start": "2026-07-01", "end": spec["data"]["end_date"]}, "symbols": records, "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
