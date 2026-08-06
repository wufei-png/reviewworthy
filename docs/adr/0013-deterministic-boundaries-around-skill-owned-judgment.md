# Keep candidate binding, understanding records, and Action checks deterministic

The Skill owns candidate explanation, contributor teaching, question selection, human answers, and Contract approval. The CLI owns only the mechanical boundaries: binding a confirmed candidate into a Packet, validating material-bound Orientation and Assessment records, and reporting deterministic Action facts. A composite GitHub Action invokes the same read-only check and never becomes an LLM gatekeeper.

## Considered Options

- Let prompt instructions copy candidates, record understanding, and decide whether a PR is acceptable.
- Build a provider-specific orchestration engine into the CLI.
- Preserve human/Skill judgment while making artifact transitions, snapshots, and deterministic Action checks machine-verifiable.

## Consequences

The workflow remains portable across Agent runtimes and exposes a stable Packet boundary. A candidate bind cannot approve a Contract, a CLI cannot invent understanding, and a GitHub Action can report objective violations without closing or publishing anything. Future onboarding providers must write the same understanding contract rather than replace these boundaries.
