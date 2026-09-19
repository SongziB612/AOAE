from __future__ import annotations

import argparse
import json
from pathlib import Path

from aoae.etf_validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite validation result: {args.output}")
    result = run_validation(args.spec, args.repo_root, args.data_dir)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "checks": result["checks"], "rolling_windows": {key: value for key, value in result["rolling_windows"].items() if key != "windows"}, "leave_one_out": result["leave_one_risk_asset_out"]}, indent=2, ensure_ascii=False))
    return 0 if result["result"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
