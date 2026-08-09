# Example contribution

This is an illustrative, non-submittable example of a bounded Reviewworthy contribution. It demonstrates the artifact flow without pretending that an Issue, a test receipt, or a PR has been approved.

## Scenario

Suppose a maintainer-owned Issue reports that an input boundary accepts an invalid value. The contributor should:

1. Verify the canonical Issue URL and inspect existing Issues and PRs.
2. Record `not_duplicate` (or another human/Skill-owned disposition) in the Candidate Menu.
3. Create a Brief with the repository identity and only explicitly selected focus-file hashes.
4. Bind the Issue basis to a Packet and approve a narrow Contract.
5. Capture the real diff and run verification at the same `head_sha`.
6. Record standard Understanding evidence for behavior, invariant, and test.
7. Preview the exact PR Body, including the Issue URL and required AI disclosure, then confirm the operation ID.

Representative commands:

```bash
PYTHONPATH=src python -m reviewworthy brief create --root . --focus src/reviewworthy/action.py
PYTHONPATH=src python -m reviewworthy diff capture --root . --base BASE_SHA --head HEAD_SHA
PYTHONPATH=src python -m reviewworthy verify run --root . --packet .git/reviewworthy/v0.3/contributions/contribution-001/packet.json --check-id unit --json
PYTHONPATH=src python -m reviewworthy understanding record .reviewworthy/contribution.json \
  --phase orientation --status passed --rubric behavior="..." \
  --rubric invariant="..." --rubric test="..."
```

The example does not authorize a remote write. A real contribution still needs current policy, a fresh material snapshot, human answers, and an explicitly confirmed remote plan.
