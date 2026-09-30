# Example contribution

This is an illustrative, non-submittable example of a bounded Reviewworthy contribution. It demonstrates the artifact flow without pretending that an Issue, a test receipt, or a PR has been approved.

## Scenario

Suppose a maintainer-owned Issue reports that an input boundary accepts an invalid value. The contributor should:

1. Run `start` with the explicit Issue and focus files; inspect existing Issues and PRs.
2. Inspect returned policy, provider evidence and the source-manifest Brief; complete contributor-owned understanding.
3. If a Candidate Menu is used, record its explicit duplicate disposition; direct Issue-backed entry does not manufacture a menu.
4. Embed a narrow Contract, obtain human approval, and record the exact verification plan.
5. Bind the real current Diff into the Packet and run verification at the same `head_sha`.
6. Complete the Standard Ownership Check for problem, scope, verification, and risks.
7. Preview the exact PR Body, including the Issue URL and required AI disclosure, then confirm the operation ID.

Representative commands:

```bash
# Replace the Issue, focus path and input files with the actual chosen contribution.
PYTHONPATH=src python -m reviewworthy start --root . --contribution-id contribution-001 \
  --issue https://github.com/OWNER/REPO/issues/123 --focus src/reviewworthy/action.py --json
PACKET=$(git rev-parse --git-path reviewworthy/v0.3/contributions/contribution-001/packet.json)
PYTHONPATH=src python -m reviewworthy next --packet "$PACKET" --json
PYTHONPATH=src python -m reviewworthy packet contract bind --packet "$PACKET" --contract contract.json --json
# Only after explicit human approval of the embedded Contract:
PYTHONPATH=src python -m reviewworthy packet contract approve --packet "$PACKET" --human-confirmed --json
PYTHONPATH=src python -m reviewworthy packet verification plan --packet "$PACKET" --input verification-plan.json --json
# Complete and commit the approved implementation before binding its clean HEAD.
PYTHONPATH=src python -m reviewworthy diff bind --root . --packet "$PACKET" --base BASE_REF --head HEAD --json
PYTHONPATH=src python -m reviewworthy verify run --root . --packet "$PACKET" --check-id unit --json
PYTHONPATH=src python -m reviewworthy packet ownership record --packet "$PACKET" --input ownership.json --json
PYTHONPATH=src python -m reviewworthy packet ai record --packet "$PACKET" --input ai-assistance.json --json
PYTHONPATH=src python -m reviewworthy packet narrative record --packet "$PACKET" --title "Fix the bounded failure" --body-file body.md --json
PYTHONPATH=src python -m reviewworthy packet narrative preview --packet "$PACKET" --json
# Only after the contributor explicitly approves the current preview/disclosure:
PYTHONPATH=src python -m reviewworthy packet narrative confirm --packet "$PACKET" --human-confirmed --json
PYTHONPATH=src python -m reviewworthy status --packet "$PACKET" --json
PYTHONPATH=src python -m reviewworthy next --packet "$PACKET" --json
```

The example does not authorize a remote write. A real contribution still needs current policy, a fresh semantic snapshot, contributor-owned answers where its profile requires them, and an explicitly confirmed remote plan.

At readiness, choose the real base/head refs, export the exact Body using narrative
preview, and run `remote plan` with those inputs. The placeholder Issue above is
illustrative. See [saved-operation recovery](../../references/remote-writes.md)
for pending writes; `next` suggests reconciliation only for an exact current
operation, while the original state can be recovered explicitly after later changes.

The hermetic tests in `tests/test_e2e.py` exercise this full typed-command journey
for Python, Node and Go tooling shapes with real Git and actual Python subprocess
receipts. Provider facts use a fake read-only transport. These fixtures do not prove
npm/Go execution, live GitHub access or remote-write permissions.
