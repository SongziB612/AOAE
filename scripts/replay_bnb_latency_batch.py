"""Independently replay a frozen latency batch and simulate delayed taker availability."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from aoae.batch_replay import compare_points, maximum_drawdown, replay_points, simulate_taker
from aoae.experiment import write_record


def block_lcb(values: list[float], block: int, draws: int, seed: int, quantile: float) -> float:
    series = np.asarray(values, dtype=float)
    if not len(series):
        return 0.0
    rng = np.random.default_rng(seed)
    blocks = int(np.ceil(len(series) / block))
    means = np.empty(draws)
    offsets = np.arange(block)
    for index in range(draws):
        starts = rng.integers(0, len(series), size=blocks)
        sample = series[((starts[:, None] + offsets) % len(series)).ravel()[: len(series)]]
        means[index] = sample.mean()
    return float(np.quantile(means, quantile))


def summarize(records: list[dict], offset: int, delay: int, spec: dict) -> dict:
    pnls: list[float] = []
    attempts = fills = 0
    actual_delays: list[int] = []
    for record in records:
        point = next(item for item in replay_points(record, [offset]))
        execution = simulate_taker(
            record,
            point,
            delay,
            float(spec["shares_per_attempt"]),
            float(spec["adverse_slippage_per_share"]),
        )
        attempts += int(execution["attempted"])
        fills += int(execution["status"] == "SIMULATED_REPRICE")
        pnls.append(float(execution["pnl"]))
        if "actual_delay_ms" in execution:
            actual_delays.append(int(execution["actual_delay_ms"]))
    return {
        "offset_seconds": offset,
        "delay_ms": delay,
        "attempts": attempts,
        "simulated_fills": fills,
        "fill_rate_per_attempt": fills / attempts if attempts else 0.0,
        "total_net_pnl_for_five_share_attempts_usd": float(sum(pnls)),
        "mean_net_pnl_per_market_usd": float(np.mean(pnls)),
        "maximum_drawdown_usd": maximum_drawdown(pnls),
        "median_actual_delay_ms": float(np.median(actual_delays)) if actual_delays else None,
        "market_pnls": pnls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    spec_bytes = args.spec.read_bytes()
    batch_bytes = args.batch.read_bytes()
    spec = json.loads(spec_bytes)
    batch = json.loads(batch_bytes)
    if any(spec.get(key) is not False for key in ("orders_authorized", "authentication_authorized", "capital_authorized")):
        raise ValueError("replay requires zero orders, authentication, and capital")
    expected_count = int(spec["source_market_count"])
    if not args.allow_partial and int(batch["completed_markets"]) != expected_count:
        raise RuntimeError("source batch has not reached the frozen market count")
    root = args.batch.parent
    paths = [root / item for item in batch["market_result_paths"]]
    if (not args.allow_partial and len(paths) != expected_count) or len({path.name for path in paths}) != len(paths):
        raise RuntimeError("source batch path count is incomplete or duplicated")
    mismatches = []
    excluded = []
    hashes = {}
    records = []
    for path in sorted(paths, key=lambda item: int(item.stem)):
        record = json.loads(path.read_text(encoding="utf-8"))
        try:
            replayed = replay_points(record, spec["decision_seconds_before_end"])
        except (KeyError, TypeError, ValueError) as error:
            excluded.append({"market": path.stem, "reason": f"{type(error).__name__}:{error}"})
            continue
        differences = compare_points(record["decision_points"], replayed)
        if differences:
            mismatches.append({"market": path.stem, "differences": differences})
            continue
        if any(point["status"] not in {"QUOTED_ONLY", "NO_ASK"} for point in replayed):
            excluded.append({"market": path.stem, "reason": "incomplete decision point"})
            continue
        records.append(record)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not args.allow_partial and len(records) != expected_count:
        raise RuntimeError(f"strict replay requires {expected_count} complete exact records, found {len(records)}")
    primary_delay = int(spec["primary_execution_delay_ms"])
    primary = [summarize(records, int(offset), primary_delay, spec) for offset in spec["decision_seconds_before_end"]]
    correction = spec["multiple_testing"]
    for item in primary:
        item["bonferroni_block_bootstrap_mean_lcb_usd"] = block_lcb(
            item["market_pnls"],
            int(correction["circular_block_length_markets"]),
            int(correction["bootstrap_draws"]),
            int(correction["bootstrap_seed"]) + int(item["offset_seconds"]),
            float(correction["bonferroni_one_sided_lower_quantile"]),
        )
        item["gate_checks"] = {
            "minimum_attempts": item["attempts"] >= int(spec["minimum_attempts_per_offset"]),
            "minimum_fill_rate": item["fill_rate_per_attempt"] >= float(spec["minimum_fill_rate_per_attempt"]),
            "positive_total_pnl": item["total_net_pnl_for_five_share_attempts_usd"] > 0,
            "positive_multiple_test_adjusted_lcb": item["bonferroni_block_bootstrap_mean_lcb_usd"] > 0,
        }
        item["passes_all_gates"] = all(item["gate_checks"].values())
    sensitivity = {
        str(delay): [
            {key: value for key, value in summarize(records, int(offset), int(delay), spec).items() if key != "market_pnls"}
            for offset in spec["decision_seconds_before_end"]
        ]
        for delay in spec["sensitivity_delays_ms"]
    }
    replay_exact = not mismatches
    gate_evaluated = len(records) == expected_count and not excluded
    passed_offsets = [item["offset_seconds"] for item in primary if item["passes_all_gates"]]
    record = {
        "schema_version": 1,
        "record_type": "independent_latency_batch_replay_and_execution_audit",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "source_batch_sha256": hashlib.sha256(batch_bytes).hexdigest(),
        "source_market_sha256": hashes,
        "source_market_count": len(records),
        "replay": {
            "exact_match_for_included_records": replay_exact,
            "gate_evaluated": gate_evaluated,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
            "excluded_count": len(excluded),
            "excluded": excluded
        },
        "primary_execution": primary,
        "sensitivity_execution": sensitivity,
        "result": {
            "status": ("PASS_AUDIT_ONLY" if replay_exact and passed_offsets else "FAIL") if gate_evaluated else "PARTIAL_DIAGNOSTIC",
            "passing_offsets_seconds": passed_offsets if gate_evaluated else [],
            "deployable": False,
            "interpretation": "Post-capture audit with REST polling; even a pass requires a new untouched WebSocket batch and cannot authorize capital.",
        },
        "orders_placed": 0,
        "authentication_used": False,
        "capital_authorized": False
    }
    write_record(args.output, record)
    print(json.dumps({"replay": record["replay"], "result": record["result"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
