from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reviewworthy.brief import build_project_brief
from reviewworthy.policy import inspect_policy


class PolicyInspectionTests(unittest.TestCase):
    def test_repository_document_conflict_is_a_hard_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("AI assistance is not allowed. Open an issue first.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text("[ai]\nallowed = true\n", encoding="utf-8")

            result = inspect_policy(root)

            self.assertEqual(result["authoritative_claims"]["ai_assistance"], "prohibited")
            self.assertEqual(result["authoritative_claims"]["issue_required"], True)
            self.assertEqual(result["result"], "blocked")
            self.assertEqual(result["hard_stops"][0]["code"], "policy_conflict")

    def test_structured_policy_fills_silent_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small example project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[ai]\nallowed = true\ndisclosure_required = true\n[contribution]\nissue_required = true\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertEqual(result["result"], "passed")
            self.assertEqual(result["authoritative_claims"]["issue_required"], True)
            self.assertEqual(result["authoritative_claims"]["disclosure_required"], True)

    def test_missing_policy_is_conservative_but_not_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_policy(Path(directory))

            self.assertEqual(result["posture"], "conservative")
            self.assertEqual(result["conflicts"], [])
            self.assertEqual(result["hard_stops"], [])

    def test_explanatory_text_does_not_become_policy_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "Issue-backed and Discovery entries converge into one flow. "
                "The README explains why disclosure is recorded and why an issue may be useful.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIsNone(result["authoritative_claims"]["issue_required"])
            self.assertIsNone(result["authoritative_claims"]["disclosure_required"])

    def test_unrelated_not_required_clause_does_not_negate_issue_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CONTRIBUTING.md").write_text(
                "A contribution must begin with a public GitHub Issue; the verified Issue may be pending, "
                "and a maintainer reply is not required before implementation.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIs(result["authoritative_claims"]["issue_required"], True)
            self.assertEqual(result["conflicts"], [])

    def test_structured_disclosure_policy_is_normalized_with_locations_and_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small example project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[ai]\nallowed = true\ndisclosure_required = true\ndisclosure_locations = ['commit_trailer']\ndisclosure_stages = ['verification']\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertEqual(result["authoritative_claims"]["disclosure_locations"], ["commit_trailer"])
            self.assertEqual(result["disclosure"]["stages"], ["verification"])

    def test_human_commit_trailer_policy_does_not_add_commit_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Contributors must disclose AI assistance in the commit trailer.\n", encoding="utf-8")

            result = inspect_policy(root)

            self.assertEqual(result["authoritative_claims"]["disclosure_locations"], ["commit_trailer"])

    def test_release_trailer_without_ai_does_not_create_disclosure_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Contributors must disclose the release trailer.\n", encoding="utf-8")

            result = inspect_policy(root)

            self.assertIsNone(result["authoritative_claims"]["disclosure_required"])

    def test_unknown_structured_ai_policy_enters_conservative_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[ai]\nallowed = 'unknown'\ndisclosure_required = false\ndisclosure_locations = ['pr_body']\ndisclosure_stages = []\n"
                "[contribution]\nissue_required = false\ndiscovery_evidence_allowed = true\ngood_first_issue_ai_allowed = true\n"
                "[pr]\nhuman_narrative_required = false\ndraft_required = false\n"
                "[security]\nprivate_reporting_required = false\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIsNone(result["authoritative_claims"]["ai_assistance"])
            self.assertIn("ai_assistance", result["unknown_claims"])
            self.assertEqual(result["posture"], "conservative")

    def test_claim_records_preserve_state_and_source_line_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Line one.\nAI assistance is prohibited for contributions.\n", encoding="utf-8")

            result = inspect_policy(root)
            record = result["claim_records"]["ai_assistance"]

            self.assertEqual(record["state"], "false")
            self.assertEqual(record["value"], "prohibited")
            self.assertTrue(record["provenance"])
            self.assertEqual(record["provenance"][0]["line_start"], 2)
            self.assertEqual(len(record["provenance"][0]["excerpt_sha256"]), 64)

    def test_same_document_opposed_claims_are_policy_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "This is a maintainer-first project.\nAI assistance is allowed for contributions.\nAI assistance is prohibited for this path.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)
            record = result["claim_records"]["ai_assistance"]

            self.assertIsNone(record["value"])
            self.assertEqual(record["state"], "unknown")
            self.assertEqual({item["line_start"] for item in record["provenance"]}, {2, 3})
            self.assertEqual(result["conflicts"], [])
            self.assertEqual(result["hard_stops"], [{"code": "policy_ambiguity", "reason": "One policy source makes opposed explicit claims."}])
            self.assertEqual(result["ambiguities"][0]["key"], "ai_assistance")
            self.assertEqual(result["result"], "blocked")

    def test_explicit_document_negatives_become_false_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CONTRIBUTING.md").write_text(
                "You are not required to open an issue.\n"
                "Disclosure of AI use is not required.\n"
                "A PR narrative does not need to be human-written.\n"
                "Security reports are not required to be private.\n"
                "A PR is not required to be draft.\n"
                "Discovery evidence is not allowed.\n"
                "AI use on a good-first-issue is not allowed.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            for key in (
                "issue_required",
                "disclosure_required",
                "human_pr_narrative_required",
                "security_private_reporting",
                "draft_pr_required",
                "discovery_evidence_allowed",
                "good_first_issue_ai_allowed",
            ):
                self.assertIs(result["authoritative_claims"][key], False, key)
            self.assertEqual(result["ambiguities"], [])
            self.assertEqual(result["conflicts"], [])

    def test_opposed_clauses_are_not_collapsed_as_one_negative_match(self) -> None:
        cases = {
            "ai_assistance": "AI assistance is allowed; AI assistance is prohibited.\n",
            "issue_required": "An issue is required; an issue is not required.\n",
            "disclosure_required": "You must disclose AI use; disclosure of AI use is not required.\n",
            "human_pr_narrative_required": "PR narrative must be human-written; PR narrative must not be human-written.\n",
            "security_private_reporting": "Security reports must be private; security reports must not be private.\n",
            "draft_pr_required": "A draft PR is required; a draft PR is not required.\n",
            "discovery_evidence_allowed": "Discovery evidence is sufficient; discovery evidence is not sufficient.\n",
            "good_first_issue_ai_allowed": "Good-first-issue AI is allowed; good-first-issue AI is prohibited.\n",
        }
        for key, content in cases.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertIn(key, {item["key"] for item in result["ambiguities"]})
                self.assertEqual(result["conflicts"], [])
                self.assertIn("policy_ambiguity", {item["code"] for item in result["hard_stops"]})

    def test_opposed_claims_joined_by_conjunction_or_comma_are_ambiguous(self) -> None:
        cases = {
            "issue_required": "An issue is required and not required.\n",
            "disclosure_required": "Contributors must disclose AI use; Contributors must not disclose AI use.\n",
            "human_pr_narrative_required": "PR narrative must be human-written, PR narrative does not need to be human-written.\n",
            "draft_pr_required": "A draft PR is required and a draft PR is not required.\n",
            "discovery_evidence_allowed": "Discovery evidence is allowed, discovery evidence is not allowed.\n",
        }
        for key, content in cases.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertIn(key, {item["key"] for item in result["ambiguities"]})
                self.assertEqual(result["result"], "blocked")

    def test_nested_negation_does_not_reverse_policy_polarity(self) -> None:
        cases = {
            "ai_not_permitted": ("AI assistance is not permitted.\n", "ai_assistance", "prohibited"),
            "ai_not_welcome": ("AI assistance is not welcome.\n", "ai_assistance", "prohibited"),
            "ai_leading_no_allowed": ("No AI assistance is allowed.\n", "ai_assistance", "prohibited"),
            "ai_leading_no_permitted": ("No AI use is permitted.\n", "ai_assistance", "prohibited"),
            "ai_unwelcome": ("AI assistance is unwelcome.\n", "ai_assistance", "prohibited"),
            "ai_disallowed": ("AI assistance is disallowed.\n", "ai_assistance", "prohibited"),
            "ai_not_prohibited": ("AI assistance is not prohibited.\n", "ai_assistance", "allowed"),
            "ai_not_unwelcome": ("AI assistance is not unwelcome.\n", "ai_assistance", "allowed"),
            "issue_not_accepted": ("A pull request is not accepted without an issue.\n", "issue_required", True),
            "issue_may_not_proceed": ("A pull request may not proceed without an issue.\n", "issue_required", True),
            "human_cannot_ai": ("A PR cannot be AI-written.\n", "human_pr_narrative_required", True),
            "human_may_not_ai": ("A PR may not be AI-written.\n", "human_pr_narrative_required", True),
            "security_cannot_public": ("Security reports cannot be public.\n", "security_private_reporting", True),
            "security_may_not_public": ("Security reports may not be public.\n", "security_private_reporting", True),
            "good_first_not_permitted": ("Good-first-issue AI is not permitted.\n", "good_first_issue_ai_allowed", False),
            "good_first_disallowed": ("Good-first-issue AI is disallowed.\n", "good_first_issue_ai_allowed", False),
            "good_first_not_prohibited": ("Good-first-issue AI is not prohibited.\n", "good_first_issue_ai_allowed", True),
            "good_first_not_unwelcome": ("Good-first-issue AI is not unwelcome.\n", "good_first_issue_ai_allowed", True),
            "discovery_disallowed": ("Discovery evidence is disallowed.\n", "discovery_evidence_allowed", False),
            "discovery_not_sufficient": ("Discovery evidence is not sufficient.\n", "discovery_evidence_allowed", False),
            "discovery_not_insufficient": ("Discovery evidence is not insufficient.\n", "discovery_evidence_allowed", True),
            "discovery_not_prohibited": ("Discovery evidence is not prohibited.\n", "discovery_evidence_allowed", True),
            "disclosure_must_not": ("Contributors must not disclose AI use.\n", "disclosure_required", False),
            "issue_not_optional": ("An issue is not optional.\n", "issue_required", True),
            "disclosure_not_optional": ("AI disclosure is not optional.\n", "disclosure_required", True),
            "human_not_optional": ("A human-written PR narrative is not optional.\n", "human_pr_narrative_required", True),
            "draft_not_optional": ("A draft PR is not optional.\n", "draft_pr_required", True),
        }
        for name, (content, key, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertEqual(result["authoritative_claims"][key], expected)
                self.assertEqual(result["ambiguities"], [])

    def test_policy_negation_tolerates_ordinary_whitespace(self) -> None:
        cases = (
            ("ai", "ai_assistance", "AI assistance is not  permitted.\n", "prohibited"),
            ("good_first", "good_first_issue_ai_allowed", "Good-first-issue AI is not  allowed.\n", False),
            ("discovery", "discovery_evidence_allowed", "Discovery evidence is not  sufficient.\n", False),
            ("disclosure_optional", "disclosure_required", "AI disclosure is not  optional.\n", True),
            ("disclosure_required", "disclosure_required", "Disclosure of AI use is not  required.\n", False),
            ("human", "human_pr_narrative_required", "A human-written PR narrative is not  optional.\n", True),
            ("draft", "draft_pr_required", "A draft PR is not  optional.\n", True),
            ("security", "security_private_reporting", "Security reports are not  required to be private.\n", False),
        )
        for name, key, content, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertEqual(result["authoritative_claims"][key], expected)

    def test_double_negation_opposition_is_ambiguous(self) -> None:
        cases = {
            "ai_assistance": "AI assistance is not prohibited and AI assistance is prohibited.\n",
            "good_first_issue_ai_allowed": "Good-first-issue AI is prohibited; Good-first-issue AI is not prohibited.\n",
            "discovery_evidence_allowed": "Discovery evidence is not insufficient and Discovery evidence is insufficient.\n",
        }
        for key, content in cases.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertIn(key, {item["key"] for item in result["ambiguities"]})
                self.assertEqual(result["result"], "blocked")

    def test_issue_precondition_opposition_is_whitespace_safe_in_either_order(self) -> None:
        cases = (
            "A pull request is not  accepted without an issue; an issue is not required.\n",
            "An issue is not required; a pull request may\tnot proceed without an issue.\n",
        )
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(content, encoding="utf-8")

                result = inspect_policy(root)

                self.assertIn("issue_required", {item["key"] for item in result["ambiguities"]})
                self.assertIsNone(result["authoritative_claims"]["issue_required"])
                self.assertEqual(result["result"], "blocked")

    def test_explicit_without_issue_and_public_ai_permissions_remain_false_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "A pull request may be opened without an issue.\n"
                "A PR may be AI-written.\n"
                "Security reports may be public.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIs(result["authoritative_claims"]["issue_required"], False)
            self.assertIs(result["authoritative_claims"]["human_pr_narrative_required"], False)
            self.assertIs(result["authoritative_claims"]["security_private_reporting"], False)

    def test_compound_issue_precondition_remains_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CONTRIBUTING.md").write_text(
                "Contributors must open an issue and obtain approval before submitting a pull request.\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)

            self.assertIs(result["authoritative_claims"]["issue_required"], True)

    def test_structured_policy_provenance_fills_silence_without_becoming_opaque_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text("[contribution]\nissue_required = true\n", encoding="utf-8")

            result = inspect_policy(root)
            record = result["claim_records"]["issue_required"]

            self.assertEqual(record["state"], "true")
            self.assertEqual(record["value"], True)
            self.assertEqual(record["provenance"][0]["source"], ".reviewworthy/policy.toml")

    def test_structured_policy_provenance_uses_the_parsed_table_not_a_same_named_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A small project.\n", encoding="utf-8")
            config_dir = root / ".reviewworthy"
            config_dir.mkdir()
            (config_dir / "policy.toml").write_text(
                "[other]\nissue_required = false\n[contribution]\nissue_required = true\n",
                encoding="utf-8",
            )

            result = inspect_policy(root)
            provenance = result["claim_records"]["issue_required"]["provenance"][0]

            self.assertIsNone(result["authoritative_claims"]["issue_required"])
            self.assertEqual(result["diagnostics"][0]["path"], ".reviewworthy/policy.toml:other")
            self.assertEqual(provenance["line_start"], 4)

    def test_defaults_ignore_release_and_tutorial_text_but_keep_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("AI assistance is allowed.\n", encoding="utf-8")
            for name in ("docs/tutorial.md", ".github/release.md", ".github/workflows/test.yml"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("AI assistance is prohibited.\n", encoding="utf-8")
            for name in (".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/bug.yml", ".github/pull_request_template/feature.md"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Contributors must disclose AI use.\n", encoding="utf-8")
            result = inspect_policy(root)
            self.assertEqual(result["result"], "passed")
            self.assertEqual(len(result["sources"]), 4)
            brief = build_project_brief(root)
            tutorial = next(source for source in brief["sources"] if source["path"] == "docs/tutorial.md")
            self.assertEqual(tutorial["kind"], "project_document")

    def test_explicit_documents_are_additive_authority_and_missing_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("AI assistance is allowed.\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs/contributing.md").write_text("AI assistance is prohibited.\n", encoding="utf-8")
            (root / ".reviewworthy").mkdir()
            config = root / ".reviewworthy/policy.toml"
            config.write_text('[discovery]\nauthoritative_documents = ["docs/contributing.md"]\n', encoding="utf-8")
            result = inspect_policy(root)
            self.assertIn("policy_conflict", {item["code"] for item in result["hard_stops"]})
            self.assertEqual({source["path"] for source in result["sources"]}, {"README.md", "docs/contributing.md", ".reviewworthy/policy.toml"})
            (root / "docs/contributing.md").unlink()
            result = inspect_policy(root)
            self.assertEqual(result["result"], "blocked")
            self.assertEqual(result["diagnostics"][0]["path"], "docs/contributing.md")
            self.assertIsNone(result["authoritative_claims"]["ai_assistance"])

    def test_invalid_configuration_has_path_bearing_diagnostics(self) -> None:
        cases = (
            ('[ai]\nallowd = true', ":ai.allowd"),
            ('[ai]\nallowed = 1', ":ai.allowed"),
            ('[ai]\ndisclosure_required = "yes"', ":ai.disclosure_required"),
            ('[ai]\ndisclosure_locations = ["bogus"]', ":ai.disclosure_locations"),
            ('[pr]\ndraft_required = []', ":pr.draft_required"),
            ('ai = true', ":ai"),
            ('[discovery]\nauthoritative_documents = "docs/policy.md"', ":discovery.authoritative_documents"),
        )
        for content, suffix in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".reviewworthy").mkdir()
                (root / ".reviewworthy/policy.toml").write_text(content, encoding="utf-8")
                result = inspect_policy(root)
                self.assertEqual(result["result"], "blocked")
                self.assertEqual(result["diagnostics"][0]["path"], ".reviewworthy/policy.toml" + suffix)

    def test_explicit_paths_require_exact_canonical_file_names(self) -> None:
        for name in ("../policy.md", "/policy.md", "./policy.md", "docs//policy.md", "docs/*.md", ".", "docs/", "C:policy.md", " "):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".reviewworthy").mkdir()
                (root / ".reviewworthy/policy.toml").write_text('[discovery]\nauthoritative_documents = [' + json.dumps(name) + ']\n', encoding="utf-8")
                self.assertEqual(inspect_policy(root)["diagnostics"][0]["code"], "policy_invalid_configuration")

    def test_accepted_aliases_are_normalized_before_validation(self) -> None:
        cases = (
            ('[ai]\nassistance_allowed = "allowed"\n[ai.disclosure]\nlocations = ["commit_trailer"]\nstages = ["verification"]', {"ai_assistance": "allowed", "disclosure_locations": ["commit_trailer"], "disclosure_stages": ["verification"]}),
            ('[contribution.ai]\nallowed = "prohibited"', {"ai_assistance": "prohibited"}),
            ('issue_required = false\ndisclosure_required = true\nhuman_pr_narrative_required = true\nsecurity_private_reporting = false\ndraft_pr_required = true\ndiscovery_evidence_allowed = true\ngood_first_issue_ai_allowed = false', {"issue_required": False, "disclosure_required": True, "human_pr_narrative_required": True, "security_private_reporting": False, "draft_pr_required": True, "discovery_evidence_allowed": True, "good_first_issue_ai_allowed": False}),
        )
        for content, expected in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".reviewworthy").mkdir()
                (root / ".reviewworthy/policy.toml").write_text(content, encoding="utf-8")
                result = inspect_policy(root)
                self.assertEqual(result["diagnostics"], [])
                for key, value in expected.items():
                    self.assertEqual(result["authoritative_claims"][key], value)
