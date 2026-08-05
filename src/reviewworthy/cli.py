"""Command-line entry point for Reviewworthy's deterministic primitives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .action import check_packet
from .github import GhClient, GhError, build_operation, load_operation_receipt, operation_receipt_path, save_operation_receipt
from .packet import readiness_blockers, skeleton_packet, validate_packet
from .policy import inspect_policy
from .risk import assess_manifest
from .util import read_json


def _print(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(value, dict) and "result" in value:
        print(f"Result: {value['result']}")
    elif isinstance(value, dict) and "conclusion" in value:
        print(f"Conclusion: {value['conclusion']}")
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _load_object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _common_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reviewworthy", description="Evidence-first, maintainer-first contribution checks")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    policy = commands.add_parser("policy", help="Inspect repository contribution policy")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_inspect = policy_commands.add_parser("inspect")
    policy_inspect.add_argument("path", nargs="?", default=".")
    _common_json(policy_inspect)

    risk = commands.add_parser("risk", help="Assess deterministic review-depth signals")
    risk_commands = risk.add_subparsers(dest="risk_command", required=True)
    risk_assess = risk_commands.add_parser("assess")
    risk_assess.add_argument("manifest", type=Path)
    _common_json(risk_assess)

    packet = commands.add_parser("packet", help="Validate a Contribution Packet")
    packet_commands = packet.add_subparsers(dest="packet_command", required=True)
    packet_init = packet_commands.add_parser("init", help="Create an incomplete Contribution Packet skeleton")
    packet_init.add_argument("--output", type=Path, default=Path(".reviewworthy/contribution.json"))
    packet_init.add_argument("--contribution-id", default="contribution-001")
    packet_init.add_argument("--mode", choices=("issue-backed", "discovery"), default="issue-backed")
    packet_init.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    _common_json(packet_init)
    packet_validate = packet_commands.add_parser("validate")
    packet_validate.add_argument("path", type=Path)
    _common_json(packet_validate)

    action = commands.add_parser("action", help="Run read-only deterministic Action checks")
    action_commands = action.add_subparsers(dest="action_command", required=True)
    action_check = action_commands.add_parser("check")
    action_check.add_argument("path", type=Path, nargs="?", default=Path(".reviewworthy/contribution.json"))
    action_check.add_argument("--changed-file", action="append", default=[])
    _common_json(action_check)

    candidate = commands.add_parser("candidate", help="Collect read-only duplicate-work evidence")
    candidate_commands = candidate.add_subparsers(dest="candidate_command", required=True)
    candidate_search = candidate_commands.add_parser("search")
    candidate_search.add_argument("--repo", required=True, help="owner/name")
    candidate_search.add_argument("--query", required=True)
    candidate_search.add_argument("--kind", choices=("issue", "pull_request", "both"), default="both")
    _common_json(candidate_search)

    remote = commands.add_parser("remote", help="Plan or explicitly execute a GitHub write")
    remote_commands = remote.add_subparsers(dest="remote_command", required=True)
    for name in ("plan", "create"):
        command = remote_commands.add_parser(name)
        command.add_argument("--packet", type=Path, required=True)
        command.add_argument("--repo", required=True, help="owner/name")
        command.add_argument("--kind", choices=("issue", "pull_request"), required=True)
        command.add_argument("--title", required=True)
        command.add_argument("--body-file", type=Path, required=True)
        command.add_argument("--base", default="main")
        command.add_argument("--head")
        if name == "create":
            command.add_argument("--confirm-operation-id", required=True)
        _common_json(command)
    return parser


def _remote_operation(args: argparse.Namespace) -> tuple[dict[str, Any], Any]:
    packet = _load_object(args.packet)
    body = args.body_file.read_text(encoding="utf-8")
    narrative = packet.get("narrative", {})
    if not isinstance(narrative, dict) or args.title.strip() != str(narrative.get("title", "")).strip():
        raise ValueError("Remote title must exactly match the approved packet narrative title")
    if body.strip() != str(narrative.get("body", "")).strip():
        raise ValueError("Remote Body must exactly match the approved packet narrative Body")
    operation = build_operation(packet, args.repo, args.kind, args.title, body, args.base, args.head)
    return packet, operation


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "policy":
            result = inspect_policy(Path(args.path))
            _print(result, args.as_json)
            return 1 if result["hard_stops"] else 0

        if args.command == "risk":
            result = assess_manifest(_load_object(args.manifest))
            _print(result, args.as_json)
            return 1 if result["hard_stops"] else 0

        if args.command == "packet":
            if args.packet_command == "init":
                if args.output.exists() and not args.force:
                    raise ValueError(f"Refusing to overwrite existing file: {args.output}; use --force to replace it")
                packet = skeleton_packet(args.contribution_id, args.mode)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result = {"created": str(args.output), "contribution_id": args.contribution_id, "mode": args.mode}
                _print(result, args.as_json)
                return 0
            result = validate_packet(_load_object(args.path))
            _print(result, args.as_json)
            return 0 if result["valid"] else 1

        if args.command == "action":
            result = check_packet(args.path, args.changed_file or None)
            _print(result, args.as_json)
            return 1 if result["conclusion"] == "failure" else 0

        if args.command == "candidate":
            kind = "pr" if args.kind == "pull_request" else args.kind
            matches = GhClient().search_candidates(args.repo, args.query, kind)
            result = {
                "repository": args.repo,
                "query": args.query,
                "matches": matches,
                "recommendation": "stop_and_review_duplicates" if matches else "no_matching_work_found",
            }
            _print(result, args.as_json)
            return 0

        if args.command == "remote":
            packet, operation = _remote_operation(args)
            payload = operation.as_dict()
            if args.remote_command == "plan":
                payload["readiness_blockers"] = readiness_blockers(packet)
                _print(payload, args.as_json)
                return 0

            if args.confirm_operation_id != operation.operation_id:
                raise ValueError("Confirmation operation ID does not match the current rendered operation")
            blockers = readiness_blockers(packet)
            if blockers:
                payload["readiness_blockers"] = blockers
                _print(payload, args.as_json)
                return 1

            receipt_path = operation_receipt_path(args.packet, operation.operation_id)
            payload["receipt_path"] = str(receipt_path)
            receipt = load_operation_receipt(receipt_path, operation)
            if receipt:
                payload.update({"outcome": "already_exists", "source": "local_receipt", "remote": receipt["remote"]})
            else:
                client = GhClient()
                existing = client.find_existing(operation)
                if existing:
                    remote = existing[0].get("url") or existing[0].get("html_url") or ""
                    save_operation_receipt(receipt_path, operation, remote)
                    payload.update({"outcome": "already_exists", "source": "remote_reconciliation", "existing": existing, "remote": remote})
                else:
                    remote = client.create(operation)
                    save_operation_receipt(receipt_path, operation, remote)
                    payload.update({"outcome": "created", "remote": remote})
            _print(payload, args.as_json)
            return 0

    except (OSError, ValueError, GhError, json.JSONDecodeError) as exc:
        error = {"error": str(exc)}
        _print(error, getattr(args, "as_json", False))
        return 2

    print("Unknown command", file=sys.stderr)
    return 2
