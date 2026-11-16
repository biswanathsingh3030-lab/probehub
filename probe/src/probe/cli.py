"""Command line entry point: `python -m probe`."""

import argparse
import json
import os
import socket
import sys
import time

from probe import _defaults, macos_service
from probe.collector import COLLECTORS, DEFAULT_CATEGORY, collect
from probe.sender import SendError, build_envelope, send


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="probe", description="Collect data and send it to ProbeHub.")
    parser.add_argument(
        "--hub-url",
        default=os.environ.get("PROBEHUB_URL", _defaults.DEFAULT_HUB_URL),
        help="hub base URL (env PROBEHUB_URL, default http://127.0.0.1:8100)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("PROBEHUB_TOKEN", _defaults.DEFAULT_TOKEN),
        help="hub API token (env PROBEHUB_TOKEN; prefer the env var, flags show up in `ps`)",
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
        result = send(args.hub_url, envelope, token=args.token)
    except SendError as exc:
        print(f"probe: send failed: {exc}", file=sys.stderr)
        return False
    print(f"probe: sent {args.category} id={result.get('id')} received_at={result.get('received_at')}")
    return True


def _positive_interval(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("interval must be a positive integer")
    return ivalue


def service_main(argv: list[str]) -> int:
    service_parser = argparse.ArgumentParser(
        prog="probe service", description="Manage the probe as a macOS launchd service."
    )
    subparsers = service_parser.add_subparsers(dest="service_command", required=True)

    install_parser = subparsers.add_parser("install", help="install the probe as a LaunchAgent")
    install_parser.add_argument(
        "--probe-id",
        default=os.environ.get("PROBE_ID") or socket.gethostname(),
        help="identifier for this client (env PROBE_ID, default hostname)",
    )
    install_parser.add_argument(
        "--category",
        choices=sorted(COLLECTORS),
        default=DEFAULT_CATEGORY,
        help=f"what to collect and send (default {DEFAULT_CATEGORY})",
    )
    install_parser.add_argument(
        "--token",
        default=os.environ.get("PROBEHUB_TOKEN", _defaults.DEFAULT_TOKEN),
        help="hub API token (env PROBEHUB_TOKEN; prefer the env var, flags show up in `ps`)",
    )
    install_parser.add_argument(
        "--interval",
        type=_positive_interval,
        default=300,
        help="seconds between sends (default 300)",
    )

    uninstall_parser = subparsers.add_parser("uninstall", help="remove the installed LaunchAgent")
    uninstall_parser.add_argument(
        "--purge",
        action="store_true",
        default=False,
        help="also delete the installed probe.pyz",
    )

    subparsers.add_parser("status", help="show whether the LaunchAgent is installed and loaded")

    service_args = service_parser.parse_args(argv)

    try:
        if service_args.service_command == "install":
            macos_service.install(
                probe_id=service_args.probe_id,
                category=service_args.category,
                token=service_args.token,
                interval=service_args.interval,
            )
        elif service_args.service_command == "uninstall":
            macos_service.uninstall(purge=service_args.purge)
        elif service_args.service_command == "status":
            macos_service.status()
    except macos_service.UnsupportedPlatformError:
        print("probe: service commands are only supported on macOS", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"probe: service {service_args.service_command} failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    if raw_argv and raw_argv[0] == "service":
        return service_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "--version":
        print(f"probe {_defaults.VERSION}")
        return 0

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
