# Compare contribution candidates with an evidence matrix instead of a single score

Candidate menus expose basis evidence, duplicate checks, value, scope, review cost, verifiability, risk, and recommendation as separate fields. Reviewworthy does not compute or accept a single AI confidence score because that would hide the maintainer-cost and project-need trade-offs the workflow is designed to preserve.

## Considered Options

- Use a single weighted candidate score.
- Let an LLM rank candidates by confidence.
- Keep the evidence fields visible and let the contributor and maintainer choose.

## Consequences

The CLI validates completeness and duplicate disposition but does not decide which candidate has the most project value. A Skill may explain the evidence, not replace the selection decision with opaque ranking.
