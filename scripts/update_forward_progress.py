"""Refresh the non-authorizing current view of ETF forward progress."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.experiment import canonical_json
from aoae.forward_progress import summarize_forward_progress


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--evaluation-start", required=True)
    parser.add_argument("--review-date", required=True)
    parser.add_argument("--initial-equity", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.snapshot_dir.glob("*.json"))
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    progress = summarize_forward_progress(snapshots, args.evaluation_start, args.review_date, args.initial_equity)
    record = {
        "schema_version": 1,
        "record_type": "forward_paper_evaluation_current_progress",
        "evaluation_start_date": args.evaluation_start,
        "scheduled_review_date": args.review_date,
        "snapshot_sha256": {str(path): sha256(path.read_bytes()).hexdigest() for path in paths},
        **progress,
        "completion_rule": "Backfilled prices cannot accelerate the review date.",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(canonical_json(record), encoding="utf-8", newline="\n")
    temporary.replace(args.output)
    print(json.dumps({key: record[key] for key in ("as_of", "processed_new_market_days", "generated_rebalances", "status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
