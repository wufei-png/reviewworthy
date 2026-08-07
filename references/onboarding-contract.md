# Project brief and orientation contract

`reviewworthy brief create` produces `.reviewworthy/project-brief.json`, a deterministic source manifest. It records repository-relative source paths, content hashes, tooling files, test paths, command hints, and policy posture. It does not claim to understand architecture or project intent. The Contribution Packet separately binds the work to a GitHub `owner/name` identity and, when available, a repository ID.

The Skill renders the JSON with `reviewworthy brief render` and fills the human sections during Orientation:

- the project problem;
- main components;
- the relevant execution path;
- constraints and testing approach;
- unwanted change patterns.

The brief is evidence for Orientation, not a replacement for the contributor explaining the selected change. Capture the implementation Diff with `reviewworthy diff capture` and test evidence with `reviewworthy verify run`; the resulting SHAs bind the evidence to one commit. A material change to the contract, Diff, verification evidence, or policy invalidates the packet's later Assessment as defined by `references/understanding-gate.md`.

`brief validate path.json` checks the artifact structure and embedded hash. Use `brief validate path.json --root .` when freshness against the current repository must also be established.

Phase 2 adds repository identity, base-SHA binding, and explicit focus-file hashes to newly generated briefs. Earlier package-phase artifacts are intentionally fail-closed rather than silently upgraded: these facts cannot be reconstructed safely after the fact. Regenerate the brief and re-record the human-owned sections when a validator reports missing Phase 2 fields.
