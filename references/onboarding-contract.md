# Project brief and orientation contract

`reviewworthy brief create` produces `.reviewworthy/project-brief.json`, a deterministic source manifest. It records repository-relative source paths, content hashes, tooling files, test paths, command hints, and policy posture. It does not claim to understand architecture or project intent. The Contribution Packet separately binds the work to a GitHub `owner/name` identity and, when available, a repository ID.

The Skill renders the JSON with `reviewworthy brief render` and fills the human sections during Orientation:

- the project problem;
- main components;
- the relevant execution path;
- constraints and testing approach;
- unwanted change patterns.

The brief supports contributor orientation but does not replace human ownership of the selected change. After the approved implementation is coherent, bind it with `reviewworthy diff bind --root . --packet ... --base BASE --head HEAD`; generic `diff capture` does not advance Packet routing. Binding checks the current clean HEAD, approved scope, and Diff budget, then updates the existing implementation result and semantic snapshot so `status/next` enters verification. Run named Packet-plan checks with `reviewworthy verify run --packet ... --check-id ...`; the canonical subject and plan digest bind evidence to the contribution. For Heightened and Learning, a material semantic change to the contract, Diff, verification outcome, or policy invalidates Orientation and Assessment as defined by `references/understanding-gate.md`.

`brief validate path.json` checks the artifact structure and embedded hash. Use `brief validate path.json --root .` when freshness against the current repository must also be established.

Phase 2 adds repository identity, base-SHA binding, and explicit focus-file hashes to newly generated briefs. Earlier package-phase artifacts are intentionally fail-closed rather than silently upgraded: these facts cannot be reconstructed safely after the fact. Regenerate the brief and re-record the human-owned sections when a validator reports missing Phase 2 fields.

From `packet init`, bind policy with `packet policy bind`, record the Issue or Signal
with `packet basis record`, verify public evidence through the existing read-only
commands, and embed the existing Contract with `packet contract bind`. Explicit
human approval uses `packet contract approve --human-confirmed` against the embedded
Contract. Use `packet review record --input FILE` for risk/review data and
`packet verification plan --input FILE` for the existing plan shape. Re-run `next`
after each operation. Known inputs produce executable commands; absent human
content produces decision hints with the relevant domain interface. Material
updates reset affected downstream evidence without rebinding old understanding
to a fresh hash. Local Signals can establish identity with
`packet basis record --signal FILE --repository OWNER/REPO`.

`reviewworthy start --root . --contribution-id contribution-001 --issue URL --focus PATH --json`
collects the same source-manifest facts and stores its Brief beside the Packet in
Git-private `reviewworthy/v0.3/contributions/contribution-001/` state. Repeat
`--focus` for additional selected files. It binds policy and the explicit Issue
when creating the Packet, verifies that Issue read-only, and returns both artifact
paths, Brief freshness findings, and derived workflow status. A provider failure
returns the saved paths and can retry against the same artifacts. An interruption
between artifact writes reuses the surviving Brief.

Repeated start preserves existing Packet decisions and Brief human sections, and
reuses an already recorded plain-Issue or Issue-Signal verification rather than
claiming a new provider check. If an implementation renames or deletes a selected
focus file, retry still returns the saved paths and next action, with an
`invalid_focus_file` freshness finding. Changed inputs need the existing typed
Packet operations; changed focus
needs deliberate Brief regeneration or a new contribution ID. A stale Brief is
reported without replacing contributor content. Start never grants Contract or
narrative approval and never creates a remote object.
