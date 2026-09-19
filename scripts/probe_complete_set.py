"""Short read-only persistence probe for one explicit complete event set."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from aoae.basket import evaluate_complete_set
from aoae.experiment import write_record


def fetch_book(token: str) -> dict:
    url = "https://clob.polymarket.com/book?" + urlencode({"token_id": token})
    request = Request(url, headers={"User-Agent": "AOAE/0.1 read-only-research"})
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except (OSError, URLError) as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"book unavailable after retries: {token}") from last_error


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit("usage: probe_complete_set.py SNAPSHOT SLUG SAMPLES INTERVAL_SECONDS OUTPUT")
    snapshot, slug, samples, interval, output = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5])
    events = json.loads(snapshot.read_bytes())
    events = events["events"] if isinstance(events, dict) else events
    event = next(item for item in events if item["slug"] == slug)
    markets = [market for market in event["markets"] if market.get("active") and not market.get("closed") and market.get("acceptingOrders") and market.get("enableOrderBook")]
    names = [str(market.get("groupItemTitle") or "").strip().lower() for market in markets]
    if not event.get("negRisk") or "other" not in names:
        raise SystemExit("refusing probe: event lacks an explicit active Other leg")
    tokens, rates = [], []
    for market in markets:
        outcomes, market_tokens = json.loads(market["outcomes"]), json.loads(market["clobTokenIds"])
        tokens.append(market_tokens[outcomes.index("Yes")])
        schedule = market.get("feeSchedule") if market.get("feesEnabled") else None
        rates.append(float(schedule["rate"]) if schedule else 0.0)
    observations = []
    for index in range(samples):
        with ThreadPoolExecutor(max_workers=min(3, len(tokens))) as pool:
            books = list(pool.map(fetch_book, tokens))
        observation = evaluate_complete_set(books, rates)
        observation["observed_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        observations.append(observation)
        if index + 1 < samples:
            time.sleep(interval)
    taker_positive = sum(item["taker"]["profitable_before_external_costs"] for item in observations)
    maker_payoffs = [item["maker"]["payoff_if_every_leg_fills"] for item in observations]
    record = {
        "schema_version": 1,
        "record_type": "exploratory_read_only_complete_set_probe",
        "event": {"title": event["title"], "slug": slug, "explicit_other_leg": True, "leg_count": len(tokens)},
        "method": {"samples": samples, "interval_seconds": interval, "orders_placed": 0, "authentication_used": False},
        "observations": observations,
        "result": {"taker_positive_samples": taker_positive, "maker_payoff_if_all_legs_fill_min": min(maker_payoffs), "maker_payoff_if_all_legs_fill_max": max(maker_payoffs), "status": "CANDIDATE" if taker_positive else "NO_TAKER_EDGE"},
        "capital_authorized": False,
        "decision": "paper_fill_study" if max(maker_payoffs) > 0 else "reject",
    }
    write_record(output, record)
    print(json.dumps(record["result"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
