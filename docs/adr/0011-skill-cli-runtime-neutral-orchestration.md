# Keep orchestration runtime-neutral behind the Skill and CLI boundary

Reviewworthy will use the portable `maintainer-first-contribution` Skill for conversation and a deterministic Python CLI/domain layer for state transitions, evidence validation, and hard-stops. The core workflow will not depend on LangGraph; a future LangGraph integration, if needed for durable waits or hosted multi-agent execution, must call the same runtime-neutral contracts rather than duplicate policy logic.

## Considered Options

- Put the entire workflow in Skill instructions and let the Agent call the CLI opportunistically.
- Make LangGraph the core workflow runtime.
- Keep domain state and gates runtime-neutral, with the Skill as the current conversational adapter and optional orchestration adapters later.

## Consequences

The Skill remains portable across Agent runtimes, while deterministic checks cannot be skipped by prompt drift. The CLI/packet contracts must expose explicit state transitions and resumable evidence. A later hosted or long-running workflow may add LangGraph without changing policy, security, or remote-write semantics.
