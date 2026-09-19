"""Capture public exchange reverse-repo quotes without placing any order."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak

from aoae.experiment import write_record


def _quote(frame, code: str) -> dict[str, object]:
    row = frame.loc[frame["代码"].astype(str) == code]
    if len(row) != 1:
        raise RuntimeError(f"expected one quote for {code}, got {len(row)}")
    item = row.iloc[0]
    fields = ["代码", "名称", "最新价", "今开", "最高", "最低", "昨收", "成交量", "成交额"]
    result: dict[str, object] = {}
    for field in fields:
        if field in frame.columns:
            value = item[field]
            result[field] = value.item() if hasattr(value, "item") else value
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # The managed local shell installs a dead-loopback proxy to enforce its
    # network boundary. This script is run only after explicit network approval.
    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "http_proxy", "https_proxy"):
        os.environ.pop(name, None)
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    record = {
        "schema_version": 1,
        "record_type": "public_reverse_repo_quote_snapshot",
        "captured_at": now,
        "source": {
            "provider": "Eastmoney",
            "transport": "AkShare 1.18.94",
            "classification": "public_nonbroker_quote_not_proof_of_executability",
        },
        "quotes": {
            "GC001": _quote(ak.bond_sh_buy_back_em(), "204001"),
            "R-001": _quote(ak.bond_sz_buy_back_em(), "131810"),
        },
        "orders_placed": 0,
        "capital_authorized": False,
    }
    digest = write_record(args.output, record)
    print(f"wrote {args.output} sha256={digest}")


if __name__ == "__main__":
    main()
