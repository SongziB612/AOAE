"""Create a non-executable manual review packet from a clean paper snapshot."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aoae.experiment import write_record
from aoae.manual_execution import prepare_manual_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    packet = prepare_manual_packet(snapshot)
    packet["snapshot_path"] = str(args.snapshot)
    packet["snapshot_sha256"] = sha256(args.snapshot.read_bytes()).hexdigest()
    write_record(args.output, packet)
    print(json.dumps({"signal_date": packet["signal_date"], "legs": packet["legs"], "orders_authorized": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
