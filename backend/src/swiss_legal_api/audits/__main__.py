"""CLI entrypoint: ``python -m swiss_legal_api.audits agent_backed``.

Prints the JSON summary returned by :func:`agent_backed_summary` so
operators can run the audit from cron without booting the API.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import agent_backed_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swiss_legal_api.audits")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "agent_backed",
        help="Print the agent-backed audit summary as JSON.",
    )
    args = parser.parse_args(argv)
    if args.cmd == "agent_backed":
        print(json.dumps(agent_backed_summary(), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
