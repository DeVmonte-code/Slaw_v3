"""CLI entrypoint: ``python -m swiss_legal_api.audits agent_backed``.

Mirrors the admin endpoint's filter set so an operator can run the
audit from cron with the same arguments the HTTP caller would use.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import agent_backed_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swiss_legal_api.audits")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "agent_backed",
        help="Print the agent-backed audit summary as JSON.",
    )
    p.add_argument(
        "--since",
        default=None,
        help=(
            "ISO-8601 timestamp; only reports generated at or after "
            "this instant are counted."
        ),
    )
    p.add_argument(
        "--entitlement-id",
        default=None,
        help="Restrict to a single entitlement (drill-down mode).",
    )
    p.add_argument(
        "--job-id",
        default=None,
        help=(
            "Restrict to a single scan run. The job_id is the "
            "report's generated_at ISO timestamp — each persisted "
            "BenefitReport row is keyed by (user_id, generated_at)."
        ),
    )
    p.add_argument(
        "--details",
        action="store_true",
        help=(
            "Include the full per-verification provenance list under "
            "'records'."
        ),
    )
    args = parser.parse_args(argv)
    if args.cmd == "agent_backed":
        print(
            json.dumps(
                agent_backed_summary(
                    since=args.since,
                    entitlement_id=args.entitlement_id,
                    job_id=args.job_id,
                    include_records=args.details,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
