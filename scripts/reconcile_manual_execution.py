"""Reconcile manually exported fills against an approved review packet."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.experiment import write_record
from aoae.manual_execution import reconcile_manual_fills


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--fills", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    fills = json.loads(args.fills.read_text(encoding="utf-8"))["fills"]
    result = reconcile_manual_fills(packet, fills)
    result.update({
        "packet_path": str(args.packet),
        "packet_sha256": sha256(args.packet.read_bytes()).hexdigest(),
        "fills_path": str(args.fills),
        "fills_sha256": sha256(args.fills.read_bytes()).hexdigest(),
    })
    write_record(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "VIOLATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
