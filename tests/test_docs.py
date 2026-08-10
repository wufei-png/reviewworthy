from __future__ import annotations

from pathlib import Path
import unittest


class ActiveDocumentationTests(unittest.TestCase):
    def test_primary_guidance_is_contributor_side_and_skill_first(self) -> None:
        root = Path(__file__).parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        example = (root / "examples" / "contribution" / "README.md").read_text(encoding="utf-8")

        definition = (
            "Reviewworthy is a contributor-side workflow for proving that an AI-assisted "
            "contribution is needed, bounded, understood, and ready for maintainer review."
        )
        self.assertIn(definition, readme)
        self.assertLess(readme.index("## Start with the Skill"), readme.index("## Workflow contract"))
        self.assertIn("The normal entry is an existing repository Issue", readme)
        self.assertIn("Discovery is an advanced entry", readme)
        self.assertIn("reviewworthy diff bind", readme)
        self.assertIn("reviewworthy diff bind", skill)
        self.assertIn("reviewworthy diff bind", example)
        self.assertNotIn("reviewworthy diff capture", example)

    def test_public_projection_does_not_become_a_maintainer_workflow(self) -> None:
        root = Path(__file__).parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        action_reference = (root / "references" / "action-and-ci.md").read_text(encoding="utf-8")
        package_metadata = (root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("not a separate maintainer-side workflow", readme)
        self.assertIn("not maintainer approval or a quality score", readme)
        self.assertIn("not a separate maintainer product", action_reference)
        self.assertIn("Contributor-side evidence", package_metadata)

    def test_live_guidance_uses_only_current_packet_paths_and_cli_flags(self) -> None:
        root = Path(__file__).parents[1]
        paths = [root / "README.md", root / "CONTRIBUTING.md", root / "SKILL.md"]
        paths.extend(sorted((root / "references").glob("*.md")))
        paths.extend(sorted((root / "examples").rglob("*.md")))
        forbidden = {
            ".reviewworthy/contribution.json": "Packet 0.3 must stay in Git-private state",
            "--changed-files-unavailable": "the Action flag was removed",
            "--from issue_only": "candidate transition derives its origin from the Packet",
            "material_snapshot": "Packet 0.3 uses semantic_snapshot",
        }

        for path in paths:
            content = path.read_text(encoding="utf-8")
            for fragment, reason in forbidden.items():
                self.assertNotIn(fragment, content, f"{path.relative_to(root)}: {reason}")
