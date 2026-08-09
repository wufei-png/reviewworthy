from __future__ import annotations

from pathlib import Path
import unittest


class ActiveDocumentationTests(unittest.TestCase):
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
