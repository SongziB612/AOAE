"""Scan project text for credential shapes and trading calls without printing matches."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


TEXT_SUFFIXES = {".py", ".ps1", ".json", ".md", ".toml", ".yml", ".yaml"}
EXCLUDED_PARTS = {".git", ".venv", ".venv-qlib", "data", "pytest-cache-files-0r61wtx3", "pytest-cache-files-8i2lzjo2"}
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "assigned_secret": re.compile(
        r"(?i)(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']"
    ),
}
TRADING_CALLS = ("place_order(", "submit_order(", "cancel_order(", "ExecutionGateway(")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    findings = {name: [] for name in SECRET_PATTERNS}
    scanned = 0
    for path in args.root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(args.root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        scanned += 1
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings[name].append(str(relative))

    paper_paths = [
        Path("scripts/daily_paper_cycle.ps1"),
        Path("scripts/fetch_sina_daily_prices.py"),
        Path("scripts/run_paper_eod.py"),
        Path("src/aoae/paper_daily.py"),
    ]
    trading_findings = {}
    for path in paper_paths:
        text = path.read_text(encoding="utf-8")
        hits = [call for call in TRADING_CALLS if call in text]
        if hits:
            trading_findings[str(path)] = hits
    checks = {
        "no_credential_shapes_found": not any(findings.values()),
        "paper_pipeline_contains_no_trading_calls": not trading_findings,
    }
    result = {
        "schema_version": 1,
        "record_type": "pre_capital_security_boundary_audit",
        "scanned_text_files": scanned,
        "finding_files_only": findings,
        "paper_pipeline_trading_call_findings": trading_findings,
        "audited_file_sha256": {str(path): sha256(path.read_bytes()).hexdigest() for path in paper_paths},
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "orders_authorized": False,
        "capital_authorized": False,
        "broker_connection_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scanned_text_files": scanned, "checks": checks, "status": result["status"]}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
