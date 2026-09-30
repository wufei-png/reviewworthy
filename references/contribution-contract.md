# Contribution Contract

The standalone contract artifact is validated with:

```bash
reviewworthy contract init --output .reviewworthy/contribution-contract.json
reviewworthy contract validate .reviewworthy/contribution-contract.json
reviewworthy contract render .reviewworthy/contribution-contract.json --output .reviewworthy/contribution-contract.md
```

It fixes the problem, non-goals, scope, invariants, design, alternatives, validation plan, risks, success criteria, and positive Diff budget before implementation. The Packet embeds the same contract fields so the final semantic snapshot covers the approved boundary.

An approved packet Contract stores `approval.contract_sha256`, a hash of those contract fields. Editing the Contract after approval makes the approval stale and blocks remote readiness until a human approves the new snapshot.

`scope.files` is the executable file allowlist. `scope.modules` may provide semantic module context but does not expand that file allowlist. When a packet has only module scope, the Action reports the file boundary as unknown because Reviewworthy has no implicit module-to-file mapping; remote readiness blocks until that evidence is made executable.

Diff changed files use exact UTF-8 repository-relative POSIX paths, including supported Unicode, tab/newline and punctuation characters. Scope allowlists must use those exact paths. NUL-delimited Git records keep paths separate from line counts; binary files remain changed files and contribute zero numstat lines. Rename detection remains disabled, so moves appear as deletion/addition paths. Unsupported byte encodings and noncanonical paths fail explicitly.

Historical Diff fields for unusual paths may contain Git quoting or incorrectly split names/statistics. Rebind the current Diff and re-run verification before planning a new remote operation; semantic identity still uses `git-raw-content-v1`, and the raw content digest algorithm is unchanged. Recover an existing saved operation with `remote reconcile --state FILE --json` using its original retained payload/operation ID; recovery does not re-render or re-capture that historical Diff.
