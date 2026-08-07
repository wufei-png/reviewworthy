# Contribution Contract

The standalone contract artifact is validated with:

```bash
reviewworthy contract init --output .reviewworthy/contribution-contract.json
reviewworthy contract validate .reviewworthy/contribution-contract.json
reviewworthy contract render .reviewworthy/contribution-contract.json --output .reviewworthy/contribution-contract.md
```

It fixes the problem, non-goals, scope, invariants, design, alternatives, validation plan, risks, success criteria, and positive Diff budget before implementation. The packet embeds the same contract fields so the final material snapshot covers the approved boundary.

An approved packet Contract stores `approval.contract_sha256`, a hash of those contract fields. Editing the Contract after approval makes the approval stale and blocks remote readiness until a human approves the new snapshot.

`scope.files` is the executable file allowlist. `scope.modules` may provide semantic module context but does not expand that file allowlist. When a packet has only module scope, the Action reports the file boundary as unknown because Reviewworthy has no implicit module-to-file mapping; remote readiness blocks until that evidence is made executable.
