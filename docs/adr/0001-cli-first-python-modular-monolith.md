# ADR-0001: CLI-first Python modular monolith

- Status: Accepted
- Date: 2026-08-22

## Context

DAGwright needs a small, inspectable foundation before implementing its `DataProduct` compiler.
The architecture roadmap describes a much larger eventual platform, but v0.0 needs fast local
feedback, one packaging model, clear module boundaries, and no distributed-systems overhead.

## Decision

Build the initial project as a Python 3.12+ modular monolith in `src/dagwright`, managed by `uv`.
Typer is the first interface and Pydantic v2 will define typed boundaries. Ruff, strict mypy,
pytest, and Hypothesis form the verification baseline. Modules may be separated later only when
measured operational needs justify independent deployment.

The deterministic domain and compiler core will remain engine-neutral. Orchestrator, compute, and
storage integrations will enter through explicit adapters in later milestones.

## Consequences

- Contributors install and verify one workspace with one command.
- Domain boundaries must be enforced through package design and review rather than network APIs.
- No Rust, service decomposition, web UI, model integration, or runtime infrastructure is introduced
  during v0.0.
- A future language or deployment change requires a new ADR and migration evidence.
