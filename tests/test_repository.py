from __future__ import annotations

import unittest

from reviewworthy.repository import repository_identity, repository_matches, repository_slugs_match, validate_repository_identity


class RepositoryIdentityTests(unittest.TestCase):
    def test_repository_identity_matches_github_slugs_case_insensitively(self) -> None:
        identity = repository_identity("Owner/Repo")

        self.assertTrue(repository_matches(identity, "owner/repo"))
        self.assertTrue(repository_slugs_match("OWNER/REPO", "owner/repo"))

    def test_repository_identity_reuses_owner_name_slug_validation(self) -> None:
        with self.assertRaises(ValueError):
            repository_identity({"owner": "owner/name", "name": "repo"})
        errors = validate_repository_identity({
            "provider": "github",
            "host": "github.com",
            "owner": "owner/name",
            "name": "repo",
            "default_branch": "main",
        })
        self.assertIn("invalid_repository_identity", {error["code"] for error in errors})
