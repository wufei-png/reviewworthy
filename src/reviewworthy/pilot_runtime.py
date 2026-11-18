"""Hermetic pilot adapter: real local Git, Packet and operation; closed provider."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest.mock import patch

from .action import check_evidence
from .contract import skeleton_contract
from .evidence import append_evidence_summary, build_evidence_summary
from .git import capture_pr_diff, run_verification
from .github import (
    GhError,
    build_operation,
    load_operation_state,
    operation_receipt_path,
    save_operation_pending,
)
from .packet import (
    readiness_blockers,
    result_record,
    semantic_snapshot,
    skeleton_packet,
    validate_packet,
)
from .packet_mutation import (
    approve_contract,
    bind_contract,
    bind_policy,
    confirm_narrative,
    maintain_packet,
    record_ai,
    record_narrative,
    record_ownership,
    record_verification_plan,
)
from .remote import inspect_operation
from .util import atomic_write_json

FIXTURE_TIME = "2026-10-09T00:00:00Z"
FIXTURE_URL = "https://github.com/example/project/issues/7"


def git(root: Path, *args: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_DATE": FIXTURE_TIME,
        "GIT_COMMITTER_DATE": FIXTURE_TIME,
    }
    return subprocess.run(
        ["git", "-C", str(root), *args],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def repository(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "pilot@example.invalid")
    git(root, "config", "user.name", "Offline Pilot")
    observations = case["observations"]
    documents = observations.get(
        "base_documents", {"README.md": "Project contribution policy.\n"}
    )
    for relative, content in documents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    policy = root / ".reviewworthy/policy.toml"
    policy.parent.mkdir(exist_ok=True)
    policy.write_text(
        observations.get("base_structured_policy", "[ai]\nallowed = true\n")
    )
    (root / "example.py").write_text("value = 1\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Fixture base")
    git(root, "checkout", "-qb", "feature")
    for relative, content in observations.get("head_documents", {}).items():
        (root / relative).write_text(content, encoding="utf-8")
    (root / "example.py").write_text("value = 2\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Fixture head")
    with patch("reviewworthy.git.utc_now", return_value=FIXTURE_TIME):
        return capture_pr_diff(root, "main", "feature")


def ready_packet(root: Path, diff: dict[str, Any], title: str) -> dict[str, Any]:
    """Construct simulated approvals through product mutations and execute a check.

    Human and public Issue facts here are fixture facts, never live verification.
    Hashes and contributor-local command receipts come from product builders.
    """
    packet = skeleton_packet("pilot-operation", "issue-backed", "example/project")
    packet["repository"].update(repository_id=101, base_sha=diff["base_tip_sha"])
    issue = "https://github.com/example/project/issues/1"
    packet["entry"]["source"] = issue
    packet["basis"] = {
        "kind": "issue",
        "references": [issue],
        "verification": {
            "status": "verified",
            "provider": "github",
            "reference": issue,
            "repository": "example/project",
            "repository_id": 101,
            "record_type": "issue",
            "host": "github.com",
            "number": 1,
            "url": issue,
            "visibility": "public",
            "verified_at": FIXTURE_TIME,
        },
    }
    packet = maintain_packet(packet, bind_policy(packet, root))
    # Keep the full Packet portable; this audit location is outside its semantic hash.
    packet["policy"]["repository"] = "."
    contract = skeleton_contract(packet["contribution_id"])
    contract.update(
        problem="Bounded fixture change",
        design="Change a fixture value",
        scope={"files": diff["changed_files"]},
        non_goals=["No network writes"],
        invariants=["Fixture remains bounded"],
        validation_plan=["Check fixture value"],
        risks=["Synthetic environment only"],
        success_criteria=["Value is two"],
        alternatives=[
            {"option": "Leave unchanged", "rejected_because": "Does not exercise head"}
        ],
    )
    packet = maintain_packet(packet, bind_contract(packet, contract))
    packet = maintain_packet(packet, approve_contract(packet, human_confirmed=True))
    plan = {
        "plan_version": "0.1",
        "checks": [
            {
                "id": "fixture",
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('example.py').read_text() == 'value = 2\\n'",
                ],
                "cwd": ".",
                "required": True,
            }
        ],
    }
    packet = maintain_packet(packet, record_verification_plan(packet, plan))
    updated = deepcopy(packet)
    updated["diff"] = diff
    updated["results"] = [
        result_record(r["node"], "passed", ["fixture input fact"])
        if r["node"] == "implementation"
        else r
        for r in updated["results"]
    ]
    packet = maintain_packet(packet, updated)
    updated = deepcopy(packet)
    with patch("reviewworthy.git.utc_now", return_value=FIXTURE_TIME):
        updated["verification"]["receipts"] = [
            run_verification(
                root,
                "HEAD",
                plan["checks"][0]["argv"],
                check_id="fixture",
                plan_digest=packet["verification"]["plan_digest"],
                subject_digest=diff["subject_digest"],
            )
        ]
    packet = maintain_packet(packet, updated)
    packet = maintain_packet(
        packet,
        record_ownership(
            packet,
            {
                "status": "passed",
                "problem": "Fixture value change",
                "scope": "Fixture files",
                "verification": "Executed value assertion",
                "risks": ["Synthetic fixture"],
            },
        ),
    )
    packet = maintain_packet(
        packet,
        record_ai(
            packet,
            {
                "used": True,
                "stages": [
                    {
                        "name": "implementation",
                        "level": "assisted",
                        "human_verified": True,
                    }
                ],
                "disclosure": {
                    "text": "AI assistance in this synthetic fixture.",
                    "locations": ["pr_body"],
                    "human_confirmed": False,
                },
            },
        ),
    )
    packet = maintain_packet(
        packet,
        record_narrative(
            packet,
            title=title,
            body=issue
            + "\nBounded fixture change.\nAI assistance in this synthetic fixture.\n",
        ),
    )
    packet = confirm_narrative(packet, human_confirmed=True)
    errors = validate_packet(packet)["errors"] + readiness_blockers(packet)
    if errors:
        raise ValueError(f"Offline Packet construction failed: {errors}")
    return packet


class OfflineProvider:
    """Closed provider. Unknown methods cannot fall through to gh or a network."""

    def __init__(self, branch: str, events: list[dict[str, Any]], state: Path) -> None:
        self.branch, self.events, self.state = branch, events, state
        self.attempts = 0

    def record(self, kind: str, **data: Any) -> None:
        self.events.append({"sequence": len(self.events), "kind": kind, "data": data})

    def verify_repository_identity(self, repo: str, repository_id: int) -> None:
        if (repo, repository_id) != ("example/project", 101):
            raise GhError("Offline immutable repository identity mismatch")
        self.record("identity_check", repository_id=repository_id)

    def find_existing(self, operation: Any) -> list[dict[str, str]]:
        matches = (
            [{"url": FIXTURE_URL}]
            if self.attempts and self.branch == "canonical"
            else []
        )
        self.record("marker_search", complete=True, matches=matches)
        return matches

    def read_operation_object(self, operation: Any, remote: str) -> dict[str, str]:
        result = {"title": operation.title, "body": operation.body}
        self.record("read_object", remote=remote, **result)
        return result

    def create(self, operation: Any) -> str:
        if self.attempts:
            raise GhError("Offline adapter allows at most one create attempt")
        _, state = load_operation_state(self.state)
        if state["status"] != "pending":
            raise GhError("Missing write-ahead pending state")
        self.attempts += 1
        self.record(
            "create_attempt", operation_id=operation.operation_id, state="pending"
        )
        if self.branch == "timeout":
            raise GhError("Offline timeout after request sent; result uncertain")
        return FIXTURE_URL


def replay(
    case: dict[str, Any], trace: dict[str, Any], work: Path, branch: str = "canonical"
) -> dict[str, Any]:
    """Replay standardized *proposed* events through a constrained local adapter."""
    from .cli import main

    if branch not in {"canonical", "timeout"}:
        raise ValueError("Unknown offline result branch")
    events: list[dict[str, Any]] = []
    root = work / "repository"
    diff = repository(root, case)
    result: dict[str, Any] = {
        "case_id": case["case_id"],
        "diff": diff,
        "events": events,
        "create_attempts": 0,
        "state_before": "none",
        "state_after": "none",
    }
    if "base_structured_policy" in case["observations"]:
        packet = skeleton_packet("pilot-action", "issue-backed", "example/project")
        packet["repository"]["repository_id"] = 101
        packet["ai_assistance"]["disclosure"]["text"] = "Fixture AI assistance"
        body = append_evidence_summary(
            "Fixture PR", build_evidence_summary(packet, diff)
        )
        checked = check_evidence(
            body,
            root=root,
            event_name="pull_request",
            event_repository="example/project",
            event_repository_id=101,
            event_base_sha=diff["base_tip_sha"],
            event_head_sha=diff["head_sha"],
            mode="evidence-enforce",
        )
        result["action_result"] = {
            "conclusion": checked["conclusion"],
            "violation_codes": sorted(v["code"] for v in checked["violations"]),
        }
        events.append(
            {"sequence": 0, "kind": "action_check", "data": result["action_result"]}
        )
        return result
    packet = ready_packet(root, diff, case["observations"]["operation"]["title"])
    packet_path = root / ".git/pilot/packet.json"
    atomic_write_json(packet_path, packet)
    body = packet_path.parent / "body.md"
    body.write_text(packet["narrative"]["body"])
    operation = build_operation(
        packet,
        "example/project",
        "issue",
        packet["narrative"]["title"],
        body.read_text(),
        "main",
    )
    state = operation_receipt_path(packet_path, operation.operation_id)
    with patch("reviewworthy.github.utc_now", return_value=FIXTURE_TIME):
        save_operation_pending(state, operation)
    provider = OfflineProvider(branch, events, state)
    result.update(
        operation=operation.as_dict(),
        state_before="pending",
        original_inputs={
            "packet": deepcopy(packet),
            "repo": "example/project",
            "kind": "issue",
            "title": packet["narrative"]["title"],
            "body": body.read_text(),
            "base": "main",
            "head": None,
        },
        packet_semantic_sha256=semantic_snapshot(packet),
    )
    # The harness enforces the Skill-owned risk/manual permission separately
    # from product readiness. The CLI cannot authenticate a human from prose.
    authorization = case["current_retry_authorization"]
    permitted = (
        all(authorization.values())
        and case["observations"]["manual_inspection"][
            "remote_objects_and_original_marker_inspected"
        ]
    )
    for event in trace["events"]:
        if event not in {
            "create_issue",
            "create_issue_once",
            "second_create_attempt",
            "remote_write",
        }:
            continue
        if not permitted or provider.attempts:
            provider.record(
                "write_blocked",
                reason="authorization_missing"
                if not permitted
                else "attempt_budget_exhausted",
            )
            continue
        output = io.StringIO()
        from . import cli

        def checked_readiness(current: dict[str, Any]) -> list[dict[str, str]]:
            blockers = readiness_blockers(current)
            provider.record(
                "readiness_check", blocker_codes=[b["code"] for b in blockers]
            )
            return blockers

        original_load = cli.load_creation_receipt

        def checked_pending(
            *args: Any, _load: Any = original_load, **kwargs: Any
        ) -> Any:
            receipt = _load(*args, **kwargs)
            provider.record("pending_validated", operation_id=operation.operation_id)
            return receipt

        def write_pending(*args: Any, **kwargs: Any) -> None:
            save_operation_pending(*args, **kwargs)
            provider.record("write_ahead_pending", operation_id=operation.operation_id)

        with (
            patch("reviewworthy.cli.GhClient", return_value=provider),
            redirect_stdout(output),
            patch("reviewworthy.github.utc_now", return_value=FIXTURE_TIME),
            patch("reviewworthy.remote.utc_now", return_value=FIXTURE_TIME),
            patch("reviewworthy.cli.readiness_blockers", side_effect=checked_readiness),
            patch(
                "reviewworthy.cli.load_creation_receipt", side_effect=checked_pending
            ),
            patch("reviewworthy.cli.save_operation_pending", side_effect=write_pending),
        ):
            code = main(
                [
                    "remote",
                    "create",
                    "--root",
                    str(root),
                    "--packet",
                    str(packet_path),
                    "--repo",
                    "example/project",
                    "--kind",
                    "issue",
                    "--title",
                    operation.title,
                    "--body-file",
                    str(body),
                    "--base",
                    "main",
                    "--confirm-operation-id",
                    operation.operation_id,
                    "--retry-uncertain",
                    "--json",
                ]
            )
        payload = json.loads(output.getvalue())
        provider.record(
            "create_result",
            exit_code=code,
            remote=payload.get("remote"),
            outcome=payload.get("outcome", "uncertain"),
        )
    if not provider.attempts:
        stored, record = load_operation_state(state)
        inspection = inspect_operation(provider, stored, record)
        provider.record(
            "inspection",
            outcome=inspection["outcome"],
            diagnostics=[d["code"] for d in inspection["diagnostics"]],
        )
    stored, record = load_operation_state(state)
    result.update(
        create_attempts=provider.attempts,
        state_after=record["status"],
        remote=record.get("remote") or record.get("known_remote"),
        operation_preserved=stored == operation,
    )
    return result
