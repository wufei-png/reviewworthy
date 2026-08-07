"""Command-line entry point for Reviewworthy's deterministic primitives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .action import check_packet
from .brief import build_project_brief, render_project_brief, validate_project_brief
from .candidate import bind_candidate, render_candidate_menu, select_candidate, skeleton_menu, validate_candidate_menu
from .contract import render_contract, skeleton_contract, validate_contract
from .disclosure import render_disclosure
from .evals import run_evals
from .git import GitError, capture_diff, resolve_ref, run_verification
from .github import (
    GhClient,
    GhError,
    build_operation,
    build_signal_operation,
    load_operation_receipt,
    operation_lock,
    operation_receipt_path,
    save_operation_link_attempted,
    save_operation_linked,
    save_operation_needs_reconciliation,
    save_operation_pending,
    save_operation_pr_created,
    save_operation_receipt,
)
from .packet import issue_link_blockers, issue_reference, material_snapshot, readiness_blockers, skeleton_packet, validate_packet
from .policy import inspect_policy
from .repository import parse_public_record, repository_matches
from .risk import assess_manifest
from .signal import SIGNAL_KINDS, SIGNAL_STATUSES, skeleton_signal, validate_signal
from .understanding import record_understanding, validate_understanding
from .util import read_json, utc_now


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


def _write_json(path: Path, value: dict[str, Any], force: bool = False) -> None:
    if path.exists() and not force:
        raise ValueError(f"Refusing to overwrite existing file: {path}; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str, force: bool = False) -> None:
    if path.exists() and not force:
        raise ValueError(f"Refusing to overwrite existing file: {path}; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _replace_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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

    brief = commands.add_parser("brief", help="Create or validate deterministic project-brief facts")
    brief_commands = brief.add_subparsers(dest="brief_command", required=True)
    brief_create = brief_commands.add_parser("create", help="Collect repository facts for Skill-owned orientation")
    brief_create.add_argument("--root", type=Path, default=Path("."))
    brief_create.add_argument("--output", type=Path, default=Path(".reviewworthy/project-brief.json"))
    brief_create.add_argument("--focus", action="append", default=[])
    brief_create.add_argument("--force", action="store_true")
    _common_json(brief_create)
    brief_validate = brief_commands.add_parser("validate")
    brief_validate.add_argument("path", type=Path)
    brief_validate.add_argument("--root", type=Path, help="Also compare the brief with the current repository source manifest")
    _common_json(brief_validate)
    brief_render = brief_commands.add_parser("render", help="Render a validated brief as Markdown")
    brief_render.add_argument("path", type=Path)
    brief_render.add_argument("--output", type=Path, required=True)
    brief_render.add_argument("--force", action="store_true")
    _common_json(brief_render)

    understanding = commands.add_parser("understanding", help="Record and validate material-bound understanding gates")
    understanding_commands = understanding.add_subparsers(dest="understanding_command", required=True)
    understanding_validate = understanding_commands.add_parser("validate")
    understanding_validate.add_argument("path", type=Path)
    _common_json(understanding_validate)
    understanding_record = understanding_commands.add_parser("record")
    understanding_record.add_argument("path", type=Path)
    understanding_record.add_argument("--phase", choices=("orientation", "assessment"), required=True)
    understanding_record.add_argument("--status", choices=("passed", "failed", "blocked", "unknown", "not_run"), required=True)
    understanding_record.add_argument("--summary", default="")
    understanding_record.add_argument("--topic", action="append", default=[])
    understanding_record.add_argument("--evidence", action="append", default=[])
    understanding_record.add_argument("--question", action="append", default=[])
    understanding_record.add_argument("--answer", action="append", default=[])
    _common_json(understanding_record)

    risk = commands.add_parser("risk", help="Assess deterministic review-depth signals")
    risk_commands = risk.add_subparsers(dest="risk_command", required=True)
    risk_assess = risk_commands.add_parser("assess")
    risk_assess.add_argument("manifest", type=Path)
    _common_json(risk_assess)

    signal = commands.add_parser("signal", help="Record and validate a Contribution Signal")
    signal_commands = signal.add_subparsers(dest="signal_command", required=True)
    signal_init = signal_commands.add_parser("init", help="Create a pending Contribution Signal artifact")
    signal_init.add_argument("--kind", choices=sorted(SIGNAL_KINDS), default="issue")
    signal_init.add_argument("--reference", default="")
    signal_init.add_argument("--evidence", action="append", default=[])
    signal_init.add_argument("--published", action="store_true", help="Mark an external Issue/Discussion reference as publicly created")
    signal_init.add_argument("--status", choices=sorted(SIGNAL_STATUSES), default="pending")
    signal_init.add_argument("--confirmed-by", default="")
    signal_init.add_argument("--confirmed-at", default="")
    signal_init.add_argument("--output", type=Path, default=Path(".reviewworthy/contribution-signal.json"))
    signal_init.add_argument("--force", action="store_true")
    _common_json(signal_init)
    signal_validate = signal_commands.add_parser("validate")
    signal_validate.add_argument("path", type=Path)
    signal_validate.add_argument("--require-confirmed", action="store_true")
    _common_json(signal_validate)
    signal_verify = signal_commands.add_parser("verify", help="Verify a public reference read-only, or record a successful result with --record")
    signal_verify.add_argument("path", type=Path)
    signal_verify.add_argument("--record", action="store_true", help="Persist a successful verification record for remote readiness")
    _common_json(signal_verify)
    signal_publish = signal_commands.add_parser("publish", help="Publish an explicit GitHub Issue signal operation")
    signal_publish_commands = signal_publish.add_subparsers(dest="signal_publish_command", required=True)
    for name in ("plan", "create"):
        command = signal_publish_commands.add_parser(name)
        command.add_argument("path", type=Path)
        command.add_argument("--repo", required=True, help="owner/name")
        command.add_argument("--title", required=True)
        command.add_argument("--body-file", type=Path, required=True)
        command.add_argument("--output", type=Path, help="Updated signal path for create; defaults to the input path")
        command.add_argument("--force", action="store_true")
        if name == "create":
            command.add_argument("--confirm-operation-id", required=True)
        _common_json(command)

    packet = commands.add_parser("packet", help="Validate a Contribution Packet")
    packet_commands = packet.add_subparsers(dest="packet_command", required=True)
    packet_init = packet_commands.add_parser("init", help="Create an incomplete Contribution Packet skeleton")
    packet_init.add_argument("--output", type=Path, default=Path(".reviewworthy/contribution.json"))
    packet_init.add_argument("--contribution-id", default="contribution-001")
    packet_init.add_argument("--mode", choices=("issue-backed", "discovery"), default="issue-backed")
    packet_init.add_argument("--repository", help="github.com owner/name")
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
    action_check.add_argument("--changed-files-provided", action="store_true", help="Treat the supplied changed-file list as authoritative, even when empty")
    action_check.add_argument("--changed-files-unavailable", action="store_true", help="Do not fall back to packet-declared changed files")
    _common_json(action_check)

    candidate = commands.add_parser("candidate", help="Collect read-only duplicate-work evidence")
    candidate_commands = candidate.add_subparsers(dest="candidate_command", required=True)
    candidate_search = candidate_commands.add_parser("search")
    candidate_search.add_argument("--repo", required=True, help="owner/name")
    candidate_search.add_argument("--query", required=True)
    candidate_search.add_argument("--kind", choices=("issue", "pull_request", "both"), default="both")
    _common_json(candidate_search)
    candidate_init = candidate_commands.add_parser("init", help="Create an empty evidence-first candidate menu")
    candidate_init.add_argument("--repository", required=True)
    candidate_init.add_argument("--project-brief", default="")
    candidate_init.add_argument("--output", type=Path, default=Path(".reviewworthy/candidates.json"))
    candidate_init.add_argument("--force", action="store_true")
    _common_json(candidate_init)
    candidate_validate = candidate_commands.add_parser("validate")
    candidate_validate.add_argument("path", type=Path)
    _common_json(candidate_validate)
    candidate_render = candidate_commands.add_parser("render")
    candidate_render.add_argument("path", type=Path)
    candidate_render.add_argument("--output", type=Path, required=True)
    candidate_render.add_argument("--force", action="store_true")
    _common_json(candidate_render)
    candidate_select = candidate_commands.add_parser("select", help="Record an explicit candidate selection")
    candidate_select.add_argument("path", type=Path)
    candidate_select.add_argument("--candidate-id", required=True)
    candidate_select.add_argument("--confirm", action="store_true")
    candidate_select.add_argument("--output", type=Path)
    candidate_select.add_argument("--force", action="store_true")
    _common_json(candidate_select)
    candidate_bind = candidate_commands.add_parser("bind", help="Bind a confirmed candidate basis to a Contribution Packet")
    candidate_bind.add_argument("--menu", type=Path, required=True)
    candidate_bind.add_argument("--packet", type=Path, required=True)
    candidate_bind.add_argument("--candidate-id")
    candidate_bind.add_argument("--output", type=Path)
    candidate_bind.add_argument("--force", action="store_true")
    _common_json(candidate_bind)

    contract = commands.add_parser("contract", help="Create or validate a Contribution Contract")
    contract_commands = contract.add_subparsers(dest="contract_command", required=True)
    contract_init = contract_commands.add_parser("init")
    contract_init.add_argument("--contribution-id", default="contribution-001")
    contract_init.add_argument("--output", type=Path, default=Path(".reviewworthy/contribution-contract.json"))
    contract_init.add_argument("--force", action="store_true")
    _common_json(contract_init)
    contract_validate = contract_commands.add_parser("validate")
    contract_validate.add_argument("path", type=Path)
    _common_json(contract_validate)
    contract_render = contract_commands.add_parser("render")
    contract_render.add_argument("path", type=Path)
    contract_render.add_argument("--output", type=Path, required=True)
    contract_render.add_argument("--force", action="store_true")
    _common_json(contract_render)

    disclosure = commands.add_parser("disclosure", help="Render a policy-aware AI-assistance disclosure")
    disclosure_commands = disclosure.add_subparsers(dest="disclosure_command", required=True)
    disclosure_render = disclosure_commands.add_parser("render")
    disclosure_render.add_argument("--packet", type=Path, required=True)
    disclosure_render.add_argument("--location")
    disclosure_render.add_argument("--output", type=Path)
    disclosure_render.add_argument("--force", action="store_true")
    _common_json(disclosure_render)

    evaluations = commands.add_parser("eval", help="Run standard-library fixture evaluations")
    evaluation_commands = evaluations.add_subparsers(dest="eval_command", required=True)
    eval_run = evaluation_commands.add_parser("run")
    eval_run.add_argument("path", type=Path, nargs="?", default=Path("evals/fixtures"))
    _common_json(eval_run)

    diff = commands.add_parser("diff", help="Capture a read-only Git diff receipt")
    diff_commands = diff.add_subparsers(dest="diff_command", required=True)
    diff_capture = diff_commands.add_parser("capture")
    diff_capture.add_argument("--root", type=Path, default=Path("."))
    diff_capture.add_argument("--base", required=True)
    diff_capture.add_argument("--head", required=True)
    diff_capture.add_argument("--output", type=Path, default=Path(".reviewworthy/diff.json"))
    diff_capture.add_argument("--force", action="store_true")
    _common_json(diff_capture)

    verify = commands.add_parser("verify", help="Execute a verification command and record its Git-bound receipt")
    verify_commands = verify.add_subparsers(dest="verify_command", required=True)
    verify_run = verify_commands.add_parser("run")
    verify_run.add_argument("--root", type=Path, default=Path("."))
    verify_run.add_argument("--head", required=True)
    verify_run.add_argument("--output", type=Path, default=Path(".reviewworthy/verification.json"))
    verify_run.add_argument("--force", action="store_true")
    verify_run.add_argument("argv", nargs=argparse.REMAINDER, help="Command to execute; place it after --")
    _common_json(verify_run)

    issue = commands.add_parser("issue", help="Verify a supporting GitHub Issue reference")
    issue_commands = issue.add_subparsers(dest="issue_command", required=True)
    issue_verify = issue_commands.add_parser("verify")
    issue_verify.add_argument("--packet", type=Path, required=True)
    issue_verify.add_argument("--record", action="store_true", help="Persist successful verification in the packet basis")
    _common_json(issue_verify)

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
        command.add_argument("--root", type=Path, default=Path("."), help="Git worktree used to resolve base/head SHAs")
        if name == "create":
            command.add_argument("--confirm-operation-id", required=True)
        _common_json(command)
    return parser


def _remote_operation(args: argparse.Namespace) -> tuple[dict[str, Any], Any]:
    packet = _load_object(args.packet)
    if not repository_matches(packet.get("repository"), args.repo):
        raise ValueError("Remote target repository must exactly match packet.repository")
    body = args.body_file.read_text(encoding="utf-8")
    narrative = packet.get("narrative", {})
    if not isinstance(narrative, dict) or args.title.strip() != str(narrative.get("title", "")).strip():
        raise ValueError("Remote title must exactly match the approved packet narrative title")
    if body.strip() != str(narrative.get("body", "")).strip():
        raise ValueError("Remote Body must exactly match the approved packet narrative Body")
    base_sha = resolve_ref(args.root, args.base) if args.kind == "pull_request" else None
    head_sha = resolve_ref(args.root, args.head) if args.kind == "pull_request" and args.head else None
    operation = build_operation(packet, args.repo, args.kind, args.title, body, args.base, args.head, base_sha, head_sha)
    return packet, operation


def _issue_revalidation_errors(packet: dict[str, Any], remote: dict[str, Any]) -> list[dict[str, str]]:
    reference = issue_reference(packet)
    repository = packet.get("repository", {})
    errors: list[dict[str, str]] = []
    if not reference:
        return [{"code": "issue_reference_required", "message": "A pull request must have a canonical supporting Issue URL.", "path": "basis.references"}]
    if not remote.get("verified"):
        errors.append({"code": "issue_revalidation_failed", "message": str(remote.get("error", "The supporting Issue could not be verified.")), "path": "basis.verification"})
        return errors
    parsed = parse_public_record(reference)
    if not parsed or remote.get("record_type") != "issue" or remote.get("repository") != f"{parsed['owner']}/{parsed['name']}":
        errors.append({"code": "issue_revalidation_repository_mismatch", "message": "The live Issue verification does not match the Packet Issue identity.", "path": "basis.verification"})
    if isinstance(repository, dict):
        expected_repository = f"{repository.get('owner')}/{repository.get('name')}"
        if remote.get("repository") != expected_repository:
            errors.append({"code": "issue_revalidation_repository_mismatch", "message": "The live Issue verification does not match packet.repository.", "path": "repository"})
        if repository.get("repository_id") is not None and remote.get("repository_id") != repository.get("repository_id"):
            errors.append({"code": "issue_revalidation_identity_mismatch", "message": "The live Issue verification has a different repository ID.", "path": "repository.repository_id"})
    state_reason = str(remote.get("state_reason", "")).strip().lower()
    if state_reason in {"not planned", "duplicate"}:
        errors.append({"code": "issue_not_actionable", "message": f"The supporting Issue is closed as {state_reason}.", "path": "basis.verification.state_reason"})
    return errors


def _verify_and_record_issue(packet: dict[str, Any], path: Path, *, record: bool) -> dict[str, Any]:
    reference = issue_reference(packet)
    if not reference:
        return {"valid": False, "verification": "not_run", "errors": [{"code": "issue_reference_required", "message": "Packet needs a canonical GitHub Issue URL.", "path": "basis.references"}]}
    remote = GhClient().verify_public_reference(reference)
    errors = _issue_revalidation_errors(packet, remote)
    result: dict[str, Any] = {"valid": not errors, "verification": "github_public_reference", "remote": remote, "errors": errors}
    if record and result["valid"]:
        basis = packet.get("basis")
        if not isinstance(basis, dict):
            raise ValueError("Packet basis must be an object")
        verification = {
            "status": "verified",
            "provider": "github",
            "reference": reference,
            "verified_at": utc_now(),
        }
        for key in ("host", "repository", "repository_id", "record_type", "number", "url", "visibility", "state", "state_reason", "locked", "labels"):
            if remote.get(key) is not None:
                verification[key] = remote[key]
        if basis.get("kind") == "issue":
            basis["verification"] = verification
        elif isinstance(basis.get("signal"), dict) and basis["signal"].get("kind") == "issue":
            basis["signal"]["verification"] = verification
        else:
            raise ValueError("Packet basis does not contain an Issue verification target")
        packet["materials"]["material_snapshot"] = material_snapshot(packet)
        _replace_json(path, packet)
        result["recorded"] = str(path)
    return result


def _canonical_remote_url(value: Any, expected_type: str, repo: str) -> str:
    parsed = parse_public_record(value)
    if not parsed or parsed.get("record_type") != expected_type or f"{parsed['owner']}/{parsed['name']}" != repo:
        raise GhError(f"GitHub returned a non-canonical {expected_type} URL for {repo}")
    return str(parsed["url"])


def _operation_diff_blockers(packet: dict[str, Any], operation: Any) -> list[dict[str, str]]:
    diff = packet.get("diff", {})
    if not isinstance(diff, dict):
        return []
    blockers: list[dict[str, str]] = []
    if diff.get("base_sha") and operation.base_sha and diff["base_sha"] != operation.base_sha:
        blockers.append({"code": "remote_base_mismatch", "message": "The current PR base SHA differs from packet.diff.base_sha; recapture evidence.", "path": "diff.base_sha"})
    if diff.get("head_sha") and operation.head_sha and diff["head_sha"] != operation.head_sha:
        blockers.append({"code": "remote_head_mismatch", "message": "The current PR head SHA differs from packet.diff.head_sha; recapture evidence.", "path": "diff.head_sha"})
    return blockers


def _link_pull_request(client: GhClient, operation: Any, receipt_path: Path, pr_url: str) -> tuple[str, str]:
    """Reconcile exactly one Issue note after a PR has been created."""

    if not operation.issue_url:
        save_operation_linked(receipt_path, operation, pr_url)
        return "linked", "no_supporting_issue"
    save_operation_link_attempted(receipt_path, operation, pr_url)
    try:
        matches = client.find_issue_link_note(operation.issue_url, pr_url)
    except GhError as exc:
        reason = str(exc)
        save_operation_needs_reconciliation(receipt_path, operation, pr_url, reason)
        return "needs_reconciliation", reason
    if matches:
        save_operation_linked(receipt_path, operation, pr_url)
        return "linked", "existing_exact_note"
    commentability = client.issue_commentability(operation.issue_url)
    if not commentability.get("commentable"):
        reason = str(commentability.get("reason", "issue_not_commentable"))
        save_operation_needs_reconciliation(receipt_path, operation, pr_url, reason)
        return "needs_reconciliation", reason
    try:
        client.add_issue_note(operation.issue_url, pr_url)
    except GhError as exc:
        reason = str(exc)
        save_operation_needs_reconciliation(receipt_path, operation, pr_url, reason)
        return "needs_reconciliation", reason
    save_operation_linked(receipt_path, operation, pr_url)
    return "linked", "created_exact_note"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "policy":
            result = inspect_policy(Path(args.path))
            _print(result, args.as_json)
            return 1 if result["hard_stops"] else 0

        if args.command == "brief":
            if args.brief_command == "create":
                brief_value = build_project_brief(args.root, args.focus)
                _write_json(args.output, brief_value, args.force)
                _print({"created": str(args.output), "source_manifest_sha256": brief_value["source_manifest_sha256"]}, args.as_json)
                return 0
            brief_value = _load_object(args.path)
            if args.brief_command == "validate":
                result = validate_project_brief(brief_value, args.root)
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            _write_text(args.output, render_project_brief(brief_value), args.force)
            _print({"rendered": str(args.output), "source_manifest_sha256": brief_value.get("source_manifest_sha256")}, args.as_json)
            return 0

        if args.command == "understanding":
            packet = _load_object(args.path)
            if args.understanding_command == "validate":
                result = validate_understanding(packet.get("understanding"), material_snapshot(packet))
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            snapshot = material_snapshot(packet)
            updated = record_understanding(
                packet,
                args.phase,
                args.status,
                snapshot,
                summary=args.summary,
                topics=args.topic,
                evidence=args.evidence,
                questions=args.question,
                answers=args.answer,
            )
            results = updated.get("results", [])
            for result_record in results if isinstance(results, list) else []:
                if not isinstance(result_record, dict) or result_record.get("node") != "understanding":
                    continue
                if args.phase == "assessment" or args.status in {"failed", "blocked", "unknown"}:
                    result_record["status"] = args.status
                    result_record["evidence"] = list(args.evidence) or [f"{args.phase}:{args.status}"]
                    result_record.setdefault("details", {})["phase"] = args.phase
            _replace_json(args.path, updated)
            result = validate_understanding(updated.get("understanding"), material_snapshot(updated))
            result["updated"] = str(args.path)
            _print(result, args.as_json)
            return 0 if result["valid"] else 1

        if args.command == "risk":
            result = assess_manifest(_load_object(args.manifest))
            _print(result, args.as_json)
            return 1 if result["hard_stops"] else 0

        if args.command == "signal":
            if args.signal_command == "init":
                signal_value = skeleton_signal(args.kind, args.reference)
                signal_value.update(
                    {
                        "evidence": args.evidence,
                        "status": args.status,
                        "published": args.published,
                        "confirmed_by": args.confirmed_by,
                        "confirmed_at": args.confirmed_at,
                    }
                )
                _write_json(args.output, signal_value, args.force)
                _print({"created": str(args.output), "kind": args.kind, "status": args.status}, args.as_json)
                return 0
            if args.signal_command == "validate":
                signal_value = _load_object(args.path)
                result = validate_signal(signal_value, require_confirmed=args.require_confirmed)
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            if args.signal_command == "verify":
                signal_value = _load_object(args.path)
                local = validate_signal(signal_value)
                structural_errors = [error for error in local["errors"] if error["code"] != "signal_not_published"]
                if structural_errors:
                    result = {"valid": False, "verification": "not_run", "errors": structural_errors}
                elif signal_value.get("kind") == "reproducible-evidence":
                    unavailable = signal_value.get("status") in {"rejected", "expired"}
                    result = {
                        "valid": not unavailable,
                        "verification": "local_only",
                        "published": False,
                        "errors": ([{"code": "signal_unavailable", "message": "The Contribution Signal was rejected or expired.", "path": "signal.status"}] if unavailable else []),
                    }
                else:
                    remote = GhClient().verify_public_reference(signal_value["reference"])
                    errors = list(local["errors"])
                    if signal_value.get("status") in {"rejected", "expired"}:
                        errors.append({"code": "signal_unavailable", "message": "The Contribution Signal was rejected or expired.", "path": "signal.status"})
                    result = {
                        "valid": bool(remote.get("verified")) and not errors,
                        "verification": "github_public_reference",
                        "remote": remote,
                        "errors": errors,
                    }
                if args.record and result["valid"]:
                    updated_signal = dict(signal_value)
                    if signal_value.get("kind") == "reproducible-evidence":
                        verification = {
                            "status": "local_only",
                            "provider": "local",
                            "reference": signal_value.get("reference", ""),
                            "verified_at": utc_now(),
                        }
                    else:
                        remote = result["remote"]
                        verification = {
                            "status": "verified",
                            "provider": remote.get("provider", "github"),
                            "reference": signal_value["reference"],
                            "verified_at": utc_now(),
                        }
                        for key in ("repository", "record_type", "number", "url", "visibility"):
                            if remote.get(key) is not None:
                                verification[key] = remote[key]
                    updated_signal["verification"] = verification
                    _replace_json(args.path, updated_signal)
                    result["recorded"] = str(args.path)
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            signal_value = _load_object(args.path)
            body = args.body_file.read_text(encoding="utf-8")
            if not args.title.strip() or not body.strip():
                raise ValueError("Signal publication requires a non-empty title and body")
            target = args.output or args.path
            publication = signal_value.get("publication")
            if signal_value.get("published") is True:
                if not isinstance(publication, dict):
                    raise ValueError("Published signal has no recorded publication identity; reconcile before publishing again")
                if not isinstance(signal_value.get("publication_subject_id"), str) or not signal_value["publication_subject_id"].strip():
                    raise ValueError("Published signal has no stable publication subject; reconcile before publishing again")
                if any(publication.get(key) != expected for key, expected in {"repo": args.repo, "title": args.title, "body": body}.items()):
                    raise ValueError("Published signal publication inputs differ from the recorded operation")
            operation = build_signal_operation(signal_value, args.repo, args.title, body)
            payload = operation.as_dict()
            if signal_value.get("published") is True and publication.get("operation_id") != operation.operation_id:
                raise ValueError("Published signal operation identity differs from the rendered operation; reconcile before publishing again")
            if args.signal_publish_command == "plan":
                _print(payload, args.as_json)
                return 0
            if args.confirm_operation_id != operation.operation_id:
                raise ValueError("Confirmation operation ID does not match the current signal publication operation")
            publish_errors = [
                error
                for error in validate_signal(signal_value)["errors"]
                if error["code"] not in {"missing_signal_reference", "signal_not_published"}
            ]
            if publish_errors:
                raise ValueError(f"Signal is not publishable: {publish_errors}")
            if signal_value.get("status") != "pending":
                raise ValueError("Only pending signals can be published")
            if target != args.path and target.exists() and not args.force:
                existing_target = _load_object(target)
                existing_publication = existing_target.get("publication")
                if not (
                    existing_target.get("published") is True
                    and existing_target.get("publication_subject_id") == operation.subject_id
                    and isinstance(existing_publication, dict)
                    and existing_publication.get("operation_id") == operation.operation_id
                    and existing_publication.get("repo") == args.repo
                    and existing_publication.get("title") == args.title
                    and existing_publication.get("body") == body
                ):
                    raise ValueError(f"Refusing to overwrite existing file: {target}; use --force to replace it")

            receipt_path = operation_receipt_path(target, operation.operation_id)
            payload["receipt_path"] = str(receipt_path)
            with operation_lock(receipt_path):
                receipt = load_operation_receipt(receipt_path, operation)
                if receipt:
                    remote = receipt["remote"]
                    payload.update({"outcome": "already_exists", "source": "local_receipt", "remote": remote})
                else:
                    client = GhClient()
                    existing = client.find_existing(operation)
                    if existing:
                        remote = existing[0].get("url") or existing[0].get("html_url") or ""
                        save_operation_receipt(receipt_path, operation, remote)
                        payload.update({"outcome": "already_exists", "source": "remote_reconciliation", "existing": existing, "remote": remote})
                    else:
                        save_operation_pending(receipt_path, operation)
                        remote = client.create(operation)
                        save_operation_receipt(receipt_path, operation, remote)
                        payload.update({"outcome": "created", "remote": remote})
            updated_signal = dict(signal_value)
            updated_signal["reference"] = remote
            updated_signal["published"] = True
            updated_signal["publication_subject_id"] = operation.subject_id
            updated_signal["publication"] = {"operation_id": operation.operation_id, "repo": args.repo, "title": args.title, "body": body}
            _replace_json(target, updated_signal)
            payload.update({"signal": str(target), "published": True})
            _print(payload, args.as_json)
            return 0

        if args.command == "packet":
            if args.packet_command == "init":
                if args.output.exists() and not args.force:
                    raise ValueError(f"Refusing to overwrite existing file: {args.output}; use --force to replace it")
                packet = skeleton_packet(args.contribution_id, args.mode, args.repository)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result = {"created": str(args.output), "contribution_id": args.contribution_id, "mode": args.mode}
                _print(result, args.as_json)
                return 0
            result = validate_packet(_load_object(args.path))
            _print(result, args.as_json)
            return 0 if result["valid"] else 1

        if args.command == "action":
            changed_files = args.changed_file if (args.changed_files_provided or args.changed_files_unavailable) else (args.changed_file or None)
            result = check_packet(args.path, changed_files)
            _print(result, args.as_json)
            return 1 if result["conclusion"] == "failure" else 0

        if args.command == "candidate":
            if args.candidate_command == "search":
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
            if args.candidate_command == "init":
                menu = skeleton_menu(args.repository)
                menu["project_brief"] = args.project_brief
                _write_json(args.output, menu, args.force)
                _print({"created": str(args.output), "repository": args.repository}, args.as_json)
                return 0
            if args.candidate_command == "bind":
                menu = _load_object(args.menu)
                packet = _load_object(args.packet)
                updated = bind_candidate(menu, packet, args.candidate_id)
                snapshot = material_snapshot(updated)
                materials = updated.setdefault("materials", {})
                if not isinstance(materials, dict):
                    raise ValueError("packet.materials must be an object")
                materials["material_snapshot"] = snapshot
                understanding = updated.get("understanding", {})
                if isinstance(understanding, dict):
                    for phase in ("orientation", "assessment"):
                        record = understanding.get(phase)
                        if isinstance(record, dict) and record.get("status") == "not_run":
                            record["material_snapshot"] = snapshot
                target = args.output or args.packet
                if target != args.packet:
                    _write_json(target, updated, args.force)
                else:
                    _replace_json(target, updated)
                _print({"updated": str(target), "candidate_id": updated["candidate_selection"]["candidate_id"], "material_snapshot": snapshot}, args.as_json)
                return 0
            menu = _load_object(args.path)
            if args.candidate_command == "select":
                updated = select_candidate(menu, args.candidate_id, confirmed=args.confirm)
                target = args.output or args.path
                if target != args.path:
                    _write_json(target, updated, args.force)
                else:
                    _replace_json(target, updated)
                _print({"updated": str(target), "selected_id": args.candidate_id, "confirmed": args.confirm}, args.as_json)
                return 0
            if args.candidate_command == "validate":
                result = validate_candidate_menu(menu)
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            _write_text(args.output, render_candidate_menu(menu), args.force)
            _print({"rendered": str(args.output), "candidate_count": len(menu.get("candidates", []))}, args.as_json)
            return 0

        if args.command == "contract":
            if args.contract_command == "init":
                contract_value = skeleton_contract(args.contribution_id)
                _write_json(args.output, contract_value, args.force)
                _print({"created": str(args.output), "contribution_id": args.contribution_id}, args.as_json)
                return 0
            contract_value = _load_object(args.path)
            if args.contract_command == "validate":
                result = validate_contract(contract_value)
                _print(result, args.as_json)
                return 0 if result["valid"] else 1
            _write_text(args.output, render_contract(contract_value), args.force)
            _print({"rendered": str(args.output), "contribution_id": contract_value.get("contribution_id")}, args.as_json)
            return 0

        if args.command == "disclosure":
            packet = _load_object(args.packet)
            result = render_disclosure(packet, args.location)
            if args.output:
                _write_text(args.output, result["text"] + "\n", args.force)
                result["output"] = str(args.output)
            _print(result, args.as_json)
            return 0

        if args.command == "eval":
            result = run_evals(args.path)
            _print(result, args.as_json)
            return 0 if result["result"] == "passed" else 1

        if args.command == "diff":
            diff_value = capture_diff(args.root, args.base, args.head)
            _write_json(args.output, diff_value, args.force)
            _print({"captured": str(args.output), **diff_value}, args.as_json)
            return 0

        if args.command == "verify":
            command_argv = list(args.argv)
            if command_argv and command_argv[0] == "--":
                command_argv = command_argv[1:]
            receipt = run_verification(args.root, args.head, command_argv)
            _write_json(args.output, receipt, args.force)
            _print({"captured": str(args.output), **receipt}, args.as_json)
            return 0 if receipt["exit_code"] == 0 else 1

        if args.command == "issue":
            packet = _load_object(args.packet)
            result = _verify_and_record_issue(packet, args.packet, record=args.record)
            _print(result, args.as_json)
            return 0 if result["valid"] else 1

        if args.command == "remote":
            packet, operation = _remote_operation(args)
            payload = operation.as_dict()
            if args.remote_command == "plan":
                blockers = readiness_blockers(packet)
                if operation.kind == "pull_request":
                    blockers.extend(issue_link_blockers(packet, operation.body))
                    blockers.extend(_operation_diff_blockers(packet, operation))
                payload["readiness_blockers"] = blockers
                _print(payload, args.as_json)
                return 0

            if args.confirm_operation_id != operation.operation_id:
                raise ValueError("Confirmation operation ID does not match the current rendered operation")
            blockers = readiness_blockers(packet)
            if operation.kind == "pull_request":
                blockers.extend(issue_link_blockers(packet, operation.body))
                blockers.extend(_operation_diff_blockers(packet, operation))
            if blockers:
                payload["readiness_blockers"] = blockers
                _print(payload, args.as_json)
                return 1

            receipt_path = operation_receipt_path(args.packet, operation.operation_id)
            payload["receipt_path"] = str(receipt_path)
            with operation_lock(receipt_path):
                receipt = load_operation_receipt(receipt_path, operation)
                if operation.kind == "pull_request":
                    if receipt:
                        status = receipt["status"]
                        if status == "linked":
                            payload.update({"outcome": "already_exists", "source": "local_receipt", "status": status, "pr_url": receipt["pr_url"], "issue_url": receipt.get("issue_url", "")})
                            _print(payload, args.as_json)
                            return 0
                        payload.update({"outcome": "needs_reconciliation", "source": "local_receipt", "status": status, "pr_url": receipt["pr_url"], "issue_url": receipt.get("issue_url", ""), "reason": receipt.get("reason", "The PR link receipt is not terminally linked.")})
                        _print(payload, args.as_json)
                        return 1

                    client = GhClient()
                    if operation.issue_url:
                        live_issue = client.verify_public_reference(operation.issue_url)
                        live_errors = _issue_revalidation_errors(packet, live_issue)
                        if live_errors:
                            payload["readiness_blockers"] = live_errors
                            _print(payload, args.as_json)
                            return 1
                    existing = client.find_existing(operation)
                    if existing:
                        pr_url = _canonical_remote_url(existing[0].get("url") or existing[0].get("html_url"), "pull_request", operation.repo)
                        source = "remote_reconciliation"
                    else:
                        save_operation_pending(receipt_path, operation)
                        pr_url = _canonical_remote_url(client.create(operation), "pull_request", operation.repo)
                        source = "created"
                    save_operation_pr_created(receipt_path, operation, pr_url)
                    link_status, link_source = _link_pull_request(client, operation, receipt_path, pr_url)
                    payload.update({"source": source, "pr_url": pr_url, "issue_url": operation.issue_url or "", "status": link_status, "link_source": link_source})
                    if link_status != "linked":
                        payload["outcome"] = "needs_reconciliation"
                        _print(payload, args.as_json)
                        return 1
                    payload["outcome"] = "created" if source == "created" else "already_exists"
                else:
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
                            save_operation_pending(receipt_path, operation)
                            remote = client.create(operation)
                            save_operation_receipt(receipt_path, operation, remote)
                            payload.update({"outcome": "created", "remote": remote})
            _print(payload, args.as_json)
            return 0

    except (OSError, ValueError, GhError, GitError, json.JSONDecodeError) as exc:
        error = {"error": str(exc)}
        _print(error, getattr(args, "as_json", False))
        return 2

    print("Unknown command", file=sys.stderr)
    return 2
