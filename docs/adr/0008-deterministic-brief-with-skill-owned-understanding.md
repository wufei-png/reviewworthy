# Keep project facts deterministic and understanding Skill-owned

The project brief is split into a machine-generated source manifest and explicit Skill/contributor-owned understanding sections. This preserves reproducible repository facts while leaving architecture explanation, execution-path interpretation, and project intent to the orientation dialogue rather than pretending a CLI inferred them.

## Considered Options

- Generate a complete project brief with an AI summary.
- Store only free-form Markdown and skip machine validation.
- Generate deterministic facts and keep explanatory sections explicitly human/Skill-owned.

## Consequences

The CLI can hash source documents, record tooling and test-path hints, and validate freshness. The Skill must still teach and complete the project understanding before a contribution contract is approved.
