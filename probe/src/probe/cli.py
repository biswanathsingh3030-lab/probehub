"""Command line entry point: `python -m probe`."""

import argparse
import json
import os
import socket
import sys
import time

from probe.collector import COLLECTORS, DEFAULT_CATEGORY, collect
from probe.sender import SendError, build_envelope, send


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="probe", description="Collect data and send it to ProbeHub.")
    parser.add_argument(
        "--hub-url",
        default=os.environ.get("PROBEHUB_URL", "http://127.0.0.1:8000"),
        help="hub base URL (env PROBEHUB_URL, default http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--probe-id",
        default=os.environ.get("PROBE_ID") or socket.gethostname(),
        help="identifier for this client (env PROBE_ID, default hostname)",
    )
    parser.add_argument(
        "--category",
        choices=sorted(COLLECTORS),
        default=DEFAULT_CATEGORY,
        help=f"what to collect and send (default {DEFAULT_CATEGORY})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0,
        help="seconds between sends; 0 sends once and exits (default 0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the JSON envelope instead of sending it",
    )
    return parser.parse_args(argv)


def run_once(args: argparse.Namespace) -> bool:
    envelope = build_envelope(args.probe_id, args.category, collect(args.category))
    if args.dry_run:
        print(json.dumps(envelope, indent=2))
        return True
    try:
        result = send(args.hub_url, envelope)
    except SendError as exc:
        print(f"probe: send failed: {exc}", file=sys.stderr)
        return False
    print(f"probe: sent {args.category} id={result.get('id')} received_at={result.get('received_at')}")
    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.interval <= 0:
        return 0 if run_once(args) else 1
    try:
        while True:
            started = time.monotonic()
            run_once(args)  # failures are logged; keep going on the next tick
            time.sleep(max(0.0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
