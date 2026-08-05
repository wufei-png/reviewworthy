# Normalize AI assistance before rendering a project-specific disclosure

AI assistance is recorded by workflow stage, assistance level, human verification, and policy-approved disclosure location. Reviewworthy renders a disclosure for the selected location and never assumes that one universal co-author or trailer convention applies across repositories.

## Considered Options

- Hard-code one AI trailer for every repository.
- Store one unstructured disclosure sentence.
- Normalize stages and locations, then render according to repository policy.

## Consequences

Structured policy can require a PR Body, commit message, commit trailer, issue Body, or another location and can name stages that need recording. Missing or ambiguous policy remains Conservative and defaults to a human-confirmed PR Body disclosure.
