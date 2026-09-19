from __future__ import annotations

import argparse
import json
from pathlib import Path

from aoae.etf_risk_validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite validation: {args.output}")
    result = run_validation(args.spec, args.repo_root, args.data_dir)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["result"]["status"], "checks": result["checks"], "rolling": result["rolling_windows"], "cost_stress": result["cost_stress"], "leave_one_out": result["leave_one_risk_asset_out"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
