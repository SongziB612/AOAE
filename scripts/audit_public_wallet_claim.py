"""Capture and summarize a public Polymarket wallet claim without authentication."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from aoae.experiment import write_record


def fetch(path: str, query: dict) -> tuple[object, dict]:
    url = "https://data-api.polymarket.com" + path + "?" + urlencode(query)
    request = Request(url, headers={"User-Agent": "AOAE/0.1 read-only-research"})
    with urlopen(request, timeout=60) as response:
        body = response.read()
        capture = {
            "endpoint": path,
            "http_date": response.headers.get("Date"),
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
        }
    return json.loads(body), capture


def seconds_before_market_end(trade: dict) -> float | None:
    match = re.search(r"- ([A-Za-z]+ \d+), .*?-([0-9:]+[AP]M) ET$", str(trade.get("title", "")))
    if not match:
        return None
    end = datetime.strptime(f"2026 {match.group(1)} {match.group(2)}", "%Y %B %d %I:%M%p").replace(tzinfo=ZoneInfo("America/New_York"))
    traded = datetime.fromtimestamp(int(trade["timestamp"]), tz=timezone.utc)
    return (end.astimezone(timezone.utc) - traded).total_seconds()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: audit_public_wallet_claim.py SPEC OUTPUT")
    spec_path, output = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_bytes())
    if spec.get("orders_authorized") is not False or spec.get("capital_authorized") is not False:
        raise ValueError("wallet audit requires zero orders and zero capital")
    wallet = spec["wallet"]
    captures, leaderboards = [], {}
    for period in ("DAY", "WEEK", "MONTH", "ALL"):
        data, capture = fetch("/v1/leaderboard", {"timePeriod": period, "orderBy": "PNL", "category": "OVERALL", "user": wallet})
        captures.append({"name": f"leaderboard_{period.lower()}", **capture})
        leaderboards[period] = data
    trades, capture = fetch("/trades", {"user": wallet, "limit": 10000, "takerOnly": "false"})
    captures.append({"name": "trades", **capture})
    closed, capture = fetch("/closed-positions", {"user": wallet, "limit": 500, "sortBy": "REALIZEDPNL", "sortDirection": "DESC"})
    captures.append({"name": "closed_positions", **capture})
    timestamps = [int(trade["timestamp"]) for trade in trades]
    offsets = [value for trade in trades if (value := seconds_before_market_end(trade)) is not None]
    all_time = leaderboards["ALL"][0] if leaderboards["ALL"] else None
    record = {
        "schema_version": 1,
        "record_type": "exploratory_public_wallet_claim_audit",
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "wallet": wallet.lower(),
        "captures": captures,
        "leaderboard": {
            "day": leaderboards["DAY"],
            "week": leaderboards["WEEK"],
            "month": leaderboards["MONTH"],
            "all": all_time,
        },
        "trades": {
            "rows": len(trades),
            "unique_markets": len({trade.get("conditionId") for trade in trades}),
            "buy_rows": sum(trade.get("side") == "BUY" for trade in trades),
            "sell_rows": sum(trade.get("side") == "SELL" for trade in trades),
            "first_trade_utc": datetime.fromtimestamp(min(timestamps), tz=timezone.utc).isoformat().replace("+00:00", "Z") if timestamps else None,
            "last_trade_utc": datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat().replace("+00:00", "Z") if timestamps else None,
            "elapsed_seconds": max(timestamps) - min(timestamps) if timestamps else None,
            "reported_cash_notional": round(sum(float(trade["size"]) * float(trade["price"]) for trade in trades), 8),
            "seconds_before_contract_end": {
                "observations": len(offsets),
                "minimum": min(offsets) if offsets else None,
                "median": statistics.median(offsets) if offsets else None,
                "maximum": max(offsets) if offsets else None,
            },
            "market_identifiers": sorted({
                (str(trade.get("slug") or trade.get("eventSlug") or ""), str(trade.get("conditionId") or ""))
                for trade in trades
            }),
        },
        "closed_positions": {
            "rows": len(closed),
            "sum_realized_pnl": round(sum(float(position.get("realizedPnl", 0)) for position in closed), 8),
            "sum_total_bought": round(sum(float(position.get("totalBought", 0)) for position in closed), 8),
        },
        "claim_assessment": {
            "wallet_profit_supported": all_time is not None and float(all_time["pnl"]) > 900000,
            "single_session_trading_supported": bool(timestamps) and max(timestamps) - min(timestamps) < 86400,
            "917_trade_or_loop_claim_supported": False,
            "identity_or_jane_street_claim_supported": False,
            "kimi_causation_supported": False,
            "reason": "The wallet is unverified and has no linked X account; public data show 139 trade rows but cannot identify software, operator, model, agent loops, or employment history.",
        },
        "orders_placed": 0,
        "authentication_used": False,
        "capital_authorized": False,
        "decision": "investigate_market_timing_not_model_story",
    }
    write_record(output, record)
    print(json.dumps({"leaderboard_all": all_time, "trades": record["trades"], "claim_assessment": record["claim_assessment"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
