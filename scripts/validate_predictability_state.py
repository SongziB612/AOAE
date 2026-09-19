"""Run the frozen development/calibration/holdout state validation once."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aoae.latency_probe import simulate_delayed_taker, taker_fee_per_share
from aoae.predictability_state import FEATURE_NAMES, extract_predictability_state
from aoae.state_validation import (
    circular_block_bootstrap_mean_lcb,
    select_largest_qualifying_buffer,
    summarize_policy,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research/opportunity_scans/0022-predictability-state-validation/spec.json"
DEFAULT_MARKETS = ROOT / "research/opportunity_scans/0021-bnb-websocket-100-market-forward/markets"
DEFAULT_OUTPUT = ROOT / "research/opportunity_scans/0022-predictability-state-validation/result.json"


def _ordered_paths(directory: Path, required: int) -> list[Path]:
    paths = list(directory.glob("*.json"))
    if len(paths) != required:
        raise RuntimeError(f"holdout remains sealed: expected exactly {required} records, found {len(paths)}")
    try:
        paths.sort(key=lambda path: int(path.stem))
    except ValueError as error:
        raise RuntimeError("market filenames must be integer start times") from error
    if len({path.stem for path in paths}) != required:
        raise RuntimeError("duplicate market start times detected")
    return paths


def _load_records(paths: list[Path]) -> list[dict[str, Any]]:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    for path, record in zip(paths, records):
        if int(record["market"]["start_epoch"]) != int(path.stem):
            raise RuntimeError(f"filename/record start-time mismatch: {path.name}")
    return records


def _point(record: dict[str, Any], offset: int) -> dict[str, Any] | None:
    return next(
        (point for point in record["decision_points"] if int(point["seconds_before_end"]) == offset),
        None,
    )


def _score_rows(
    records: list[dict[str, Any]],
    states: list[dict[str, Any]],
    probabilities: np.ndarray,
    offset: int,
    delay_ms: int,
    shares: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    probability_index = 0
    for record, state in zip(records, states):
        row: dict[str, Any] = {
            "market_slug": record["market"]["slug"],
            "start_epoch": int(record["market"]["start_epoch"]),
            "eligible": bool(state.get("eligible")),
        }
        if not state.get("eligible"):
            row["reason"] = state.get("reason")
            output.append(row)
            continue
        q_hat = float(probabilities[probability_index])
        probability_index += 1
        ask = float(state["features"]["signaled_ask"])
        fee_rate = float(record["fee"]["rate"])
        fee_exponent = float(record["fee"].get("exponent", 1.0))
        fee = taker_fee_per_share(ask, fee_rate, fee_exponent)
        decision = _point(record, offset)
        execution = simulate_delayed_taker(
            record["evidence"]["book_snapshots"], decision or {}, delay_ms, shares, fee_rate, fee_exponent
        )
        row.update(
            {
                "q_hat": q_hat,
                "visible_ask": ask,
                "visible_fee_per_share": fee,
                "estimated_edge": q_hat - ask - fee,
                "signal_correct": bool(state["signal_correct"]),
                "execution_status": execution["status"],
                "delayed_net_pnl": float(execution.get("net_pnl", 0.0)),
            }
        )
        output.append(row)
    return output


def _predict_eligible(
    model: LogisticRegression, scaler: StandardScaler, states: list[dict[str, Any]]
) -> np.ndarray:
    matrix = [
        [float(state["features"][name]) for name in FEATURE_NAMES]
        for state in states
        if state.get("eligible")
    ]
    if not matrix:
        return np.asarray([], dtype=float)
    return model.predict_proba(scaler.transform(np.asarray(matrix, dtype=float)))[:, 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    split = spec["market_split_by_start_time"]
    required = int(split["untouched_holdout"][1])
    paths = _ordered_paths(args.markets, required)
    offset = int(spec["primary_decision_seconds_before_end"])
    depth = float(spec["minimum_initial_and_execution_depth"])
    calibration_end = int(split["calibration"][1])
    pre_holdout_records = _load_records(paths[:calibration_end])
    pre_holdout_states = [extract_predictability_state(record, offset, depth) for record in pre_holdout_records]

    def pre_holdout_section(name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        first, last = (int(value) for value in split[name])
        return pre_holdout_records[first - 1 : last], pre_holdout_states[first - 1 : last]

    development_records, development_states = pre_holdout_section("development")
    eligible_development = [state for state in development_states if state.get("eligible")]
    labels = np.asarray([int(state["signal_correct"]) for state in eligible_development], dtype=int)
    base_result: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "predictability_state_validation_result",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_market_count": len(paths),
        "feature_names": list(FEATURE_NAMES),
        "orders_placed": 0,
        "capital_authorized": False,
    }
    if len(eligible_development) < 10 or len(set(labels.tolist())) < 2:
        base_result.update(
            {
                "decision": "REJECT_INSUFFICIENT_DEVELOPMENT_DATA",
                "development_eligible": len(eligible_development),
                "holdout_opened": False,
            }
        )
        args.output.write_text(json.dumps(base_result, indent=2), encoding="utf-8")
        return 0

    matrix = np.asarray(
        [[float(state["features"][name]) for name in FEATURE_NAMES] for state in eligible_development],
        dtype=float,
    )
    scaler = StandardScaler().fit(matrix)
    model = LogisticRegression(
        penalty="l2",
        C=float(spec["model"]["C"]),
        solver=str(spec["model"]["solver"]),
        random_state=int(spec["model"]["random_state"]),
    ).fit(scaler.transform(matrix), labels)
    calibration_records, calibration_states = pre_holdout_section("calibration")
    calibration_rows = _score_rows(
        calibration_records,
        calibration_states,
        _predict_eligible(model, scaler, calibration_states),
        offset,
        int(spec["execution_delay_ms"]),
        float(spec["shares_per_attempt"]),
    )
    selected, calibration_summaries = select_largest_qualifying_buffer(
        calibration_rows, spec["calibration_edge_buffers"], minimum_attempts=10
    )
    base_result.update(
        {
            "development": {
                "markets": len(development_records),
                "eligible": len(eligible_development),
                "positive_labels": int(labels.sum()),
                "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(),
                "model_intercept": model.intercept_.tolist(),
                "model_coefficients": model.coef_[0].tolist(),
            },
            "calibration": {"summaries": calibration_summaries, "selected_buffer": selected},
        }
    )
    if selected is None:
        base_result.update({"decision": "REJECT_AT_CALIBRATION", "holdout_opened": False})
        args.output.write_text(json.dumps(base_result, indent=2), encoding="utf-8")
        return 0

    holdout_first, holdout_last = (int(value) for value in split["untouched_holdout"])
    holdout_records = _load_records(paths[holdout_first - 1 : holdout_last])
    holdout_states = [extract_predictability_state(record, offset, depth) for record in holdout_records]
    holdout_rows = _score_rows(
        holdout_records,
        holdout_states,
        _predict_eligible(model, scaler, holdout_states),
        offset,
        int(spec["execution_delay_ms"]),
        float(spec["shares_per_attempt"]),
    )
    policy = summarize_policy(holdout_rows, selected)
    baseline = summarize_policy(holdout_rows, None)
    gate = spec["holdout_gate"]
    lcb = circular_block_bootstrap_mean_lcb(
        policy["market_pnls"],
        int(gate["block_length_markets"]),
        int(gate["bootstrap_draws"]),
        int(gate["bootstrap_seed"]),
    )
    checks = {
        "minimum_attempts": policy["attempts"] >= int(gate["minimum_attempts"]),
        "positive_total_pnl": policy["total_delayed_net_pnl"] > 0,
        "beats_unconditional_baseline": policy["total_delayed_net_pnl"] > baseline["total_delayed_net_pnl"],
        "maximum_drawdown": policy["maximum_drawdown"] <= float(gate["maximum_drawdown_usd"]),
        "positive_bootstrap_lcb": lcb > 0,
    }
    base_result.update(
        {
            "decision": "CONTINUE_SIMULATION" if all(checks.values()) else "REJECT_AT_HOLDOUT",
            "holdout_opened": True,
            "holdout": {
                "policy": policy,
                "unconditional_same_signal_baseline": baseline,
                "block_bootstrap_mean_pnl_lower_95pct_bound": lcb,
                "gate_checks": checks,
                "rows": holdout_rows,
            },
        }
    )
    args.output.write_text(json.dumps(base_result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
