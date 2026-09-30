# Understanding gate

Understanding is responsibility-building, not proof of authorship.

1. **Orientation** explains the selected basis, approved contribution contract, final Diff, verification evidence, policy result, and the highest-risk path.
2. **Assessment** asks new questions about those materials. The questions must not merely ask the contributor to repeat the Orientation.
3. Both records bind to the semantic snapshot they evaluated. Any semantic change to the entry, basis, contract, Diff, verification outcome, or policy result invalidates the old record.

`standard` uses the light Ownership Check and does not require Orientation or Assessment. `heightened` and `learning` add both phases and require `behavior`, `invariant`, `test`, `flow`, `tradeoffs`, `failures`, and `regressions`. Risk signals can raise Standard to Heightened; Learning is an explicit educational profile.

Record a review section (`profile`, `signals`, `hard_stops`) or the JSON result of
`reviewworthy risk assess MANIFEST --json` through
`reviewworthy packet review record --packet "$PACKET" --input FILE --json`.
Recording merges risk signals and independent hard stops and permits only profile
escalation. An empty list or lower requested profile does not remove earlier
scrutiny. This command does not resolve hard stops; their explicit decision remains
outside this recording interface. A material review change resets downstream
verification, Ownership and understanding without changing Contract approval.

Before implementation, record the Packet's existing verification plan shape:

```bash
reviewworthy packet verification plan --packet "$PACKET" --input verification-plan.json --json
```

The input has `plan_version: "0.1"` and `checks`, each with a unique `id`, nonempty
`argv`, canonical repository-relative `cwd` (including `.`), and boolean `required`.
The CLI computes `plan_digest`; argv stays an argument list with no shell expansion.
Diff binding and `verify run` maintain the implementation/verification flow results.
Partial required checks remain `not_run`, failed required checks are `failed`, and
stale or unstable receipts are `blocked`; only exact current passing receipts
complete verification. Re-running a check replaces its receipt. A semantic outcome
change resets Ownership, understanding and final narrative confirmation; timestamps
and output hashes alone preserve them. Ownership updates preserve executed receipts.

Changing the plan resets receipts and downstream evidence; an identical plan
preserves them. Neither input accepts arbitrary Packet records or supplied hashes.

The deterministic CLI records the evidence without generating the explanation or answers. The JSON Schema validates the portable shape; `reviewworthy understanding validate` is the canonical check for rubric categories/evidence shape, equal question/answer counts, exact semantic snapshots, and phase ordering. It cannot prove that the contributor's explanation is correct:

```bash
reviewworthy understanding record .git/reviewworthy/v0.3/contributions/contribution-001/packet.json \
  --phase orientation --status passed \
  --summary "The contributor explained the selected boundary and its risks." \
  --rubric behavior="The boundary rejects invalid input." \
  --rubric invariant="Existing callers retain their behavior." \
  --rubric test="The focused test covers the regression." \
  --topic contract --topic diff --topic verification --topic policy
reviewworthy understanding record .git/reviewworthy/v0.3/contributions/contribution-001/packet.json \
  --phase assessment --status passed \
  --question "Which invariant does the changed path protect?" \
  --answer "The input boundary preserves the existing caller contract." \
  --rubric behavior="The invalid input follows the guarded path." \
  --rubric invariant="The caller contract remains unchanged." \
  --rubric test="The regression command covers the changed path."
reviewworthy understanding validate .git/reviewworthy/v0.3/contributions/contribution-001/packet.json
```

Assessment recording requires a passed Orientation bound to the current snapshot. The Skill remains responsible for teaching and for choosing non-repeating questions.
