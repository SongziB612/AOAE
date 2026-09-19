"""Command-line interface for running and independently verifying experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from aoae.contracts import ContractError, load_spec
from aoae.data_admission import audit_data_file
from aoae.experiment import canonical_json, record_digest, run_experiment, write_record
from aoae.negative_control import load_negative_control_spec, run_negative_control
from aoae.prediction_data import audit_public_events_file, capture_public_events
from aoae.real_hypothesis import run_yield_comovement_file
from aoae.slope_hypothesis import run_slope_structure_file
from aoae.temporal_hypothesis import run_slope_reversal_file
from aoae.sensitivity import run_sensitivity
from aoae.sensitivity_contracts import load_sensitivity_spec
from aoae.treasury_curve import derive_treasury_curve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aoae")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run a preregistered experiment")
    run.add_argument("--spec", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--replace", action="store_true", help="explicitly replace an existing record")

    verify = subparsers.add_parser("verify", help="recompute and compare a committed record byte-for-byte")
    verify.add_argument("--spec", type=Path, required=True)
    verify.add_argument("--expected", type=Path, required=True)

    sensitivity_run = subparsers.add_parser(
        "sensitivity-run", help="run a preregistered multi-seed sensitivity experiment"
    )
    sensitivity_run.add_argument("--spec", type=Path, required=True)
    sensitivity_run.add_argument("--output", type=Path, required=True)
    sensitivity_run.add_argument("--replace", action="store_true")

    sensitivity_verify = subparsers.add_parser(
        "sensitivity-verify", help="recompute and compare a multi-seed record byte-for-byte"
    )
    sensitivity_verify.add_argument("--spec", type=Path, required=True)
    sensitivity_verify.add_argument("--expected", type=Path, required=True)

    negative_run = subparsers.add_parser("negative-run", help="run an IID negative-control rejection experiment")
    negative_run.add_argument("--spec", type=Path, required=True)
    negative_run.add_argument("--output", type=Path, required=True)
    negative_run.add_argument("--replace", action="store_true")

    negative_verify = subparsers.add_parser("negative-verify", help="recompute and compare a negative-control record")
    negative_verify.add_argument("--spec", type=Path, required=True)
    negative_verify.add_argument("--expected", type=Path, required=True)

    data_audit = subparsers.add_parser("data-audit", help="audit a real-data snapshot against its admission contract")
    data_audit.add_argument("--spec", type=Path, required=True)
    data_audit.add_argument("--repo-root", type=Path, required=True)
    data_audit.add_argument("--output", type=Path, required=True)
    data_audit.add_argument("--replace", action="store_true")

    prediction_capture = subparsers.add_parser("prediction-data-capture", help="capture the locked first public event snapshot")
    prediction_capture.add_argument("--spec", type=Path, required=True)
    prediction_capture.add_argument("--repo-root", type=Path, required=True)
    prediction_capture.add_argument("--preregistration-commit", required=True)
    prediction_capture.add_argument("--output", type=Path, required=True)
    prediction_capture.add_argument("--replace", action="store_true")

    prediction_audit = subparsers.add_parser("prediction-data-audit", help="audit an already preserved public event snapshot")
    prediction_audit.add_argument("--spec", type=Path, required=True)
    prediction_audit.add_argument("--repo-root", type=Path, required=True)
    prediction_audit.add_argument("--captured-at-utc", required=True)
    prediction_audit.add_argument("--http-date")
    prediction_audit.add_argument("--preregistration-commit", required=True)
    prediction_audit.add_argument("--output", type=Path, required=True)
    prediction_audit.add_argument("--replace", action="store_true")

    derive_curve = subparsers.add_parser("derive-treasury", help="build the governed canonical Treasury curve table")
    derive_curve.add_argument("--spec", type=Path, required=True)
    derive_curve.add_argument("--repo-root", type=Path, required=True)
    derive_curve.add_argument("--output", type=Path, required=True)
    derive_curve.add_argument("--replace", action="store_true")

    hypothesis_run = subparsers.add_parser("hypothesis-run", help="execute one locked real-data hypothesis")
    hypothesis_run.add_argument("--spec", type=Path, required=True)
    hypothesis_run.add_argument("--repo-root", type=Path, required=True)
    hypothesis_run.add_argument("--preregistration-commit", required=True)
    hypothesis_run.add_argument("--output", type=Path, required=True)
    hypothesis_run.add_argument("--replace", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prediction-data-audit":
            record = audit_public_events_file(args.spec, args.repo_root, args.captured_at_utc, args.http_date, args.preregistration_commit)
        elif args.command == "prediction-data-capture":
            if args.output.exists() and not args.replace:
                raise FileExistsError(f"refusing capture because output record already exists: {args.output}")
            record = capture_public_events(args.spec, args.repo_root, args.preregistration_commit)
        elif args.command == "hypothesis-run":
            hypothesis_id = json.loads(args.spec.read_text(encoding="utf-8")).get("hypothesis_id")
            if hypothesis_id == "HYP-0001-treasury-yield-comovement":
                record = run_yield_comovement_file(args.spec, args.repo_root, args.preregistration_commit)
            elif hypothesis_id == "HYP-0002-treasury-slope-inversion":
                record = run_slope_structure_file(args.spec, args.repo_root, args.preregistration_commit)
            elif hypothesis_id == "HYP-0003-treasury-slope-change-reversal":
                record = run_slope_reversal_file(args.spec, args.repo_root, args.preregistration_commit)
            else:
                raise ContractError(f"unsupported real-data hypothesis: {hypothesis_id}")
        elif args.command == "derive-treasury":
            record = derive_treasury_curve(args.spec, args.repo_root, replace=args.replace)
        elif args.command == "data-audit":
            record = audit_data_file(args.spec, args.repo_root)
        elif args.command.startswith("negative-"):
            negative_spec = load_negative_control_spec(args.spec)
            record = run_negative_control(negative_spec)
        elif args.command.startswith("sensitivity-"):
            sensitivity_spec, base_spec = load_sensitivity_spec(args.spec)
            record = run_sensitivity(sensitivity_spec, base_spec)
        else:
            spec = load_spec(args.spec)
            record = run_experiment(spec)
        recomputed = canonical_json(record)

        if args.command in {"run", "sensitivity-run", "negative-run", "data-audit", "derive-treasury", "hypothesis-run", "prediction-data-capture", "prediction-data-audit"}:
            digest = write_record(args.output, record, replace=args.replace)
            print(f"record={args.output}")
            print(f"sha256={digest}")
            print(f"decision={record['decision']}")
            return 0 if record["result"]["status"] == "PASS" else 1

        expected = args.expected.read_text(encoding="utf-8")
        if expected != recomputed:
            print("verification=FAIL", file=sys.stderr)
            print(f"expected_sha256={record_digest(expected)}", file=sys.stderr)
            print(f"actual_sha256={record_digest(recomputed)}", file=sys.stderr)
            return 1
        print("verification=PASS")
        print(f"sha256={record_digest(recomputed)}")
        print(f"decision={record['decision']}")
        return 0
    except (ContractError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
