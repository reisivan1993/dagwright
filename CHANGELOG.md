# Changelog

## Unreleased

- Hardened v0.2 verification with semantic suite validation, exact negative-control expectations,
  all five quality-rule evaluators, controlled-failure evidence, and isolated wheel verification.
- Added contribution templates and transparent release/Apache-style readiness checklists.

- Added the first v0.2 checkpoint: real local Spark 3.5/Iceberg execution of the generated customer
  analytics workload with deterministic fixtures, output/schema checks, quality negative controls,
  retry/idempotency proof, and a strict golden execution-evidence manifest.
- Added `make verify-reference` and `dagwright inspect-evidence`; local compilation and execution
  remain independent of PostgreSQL and control-plane services.

## 0.1.0 — 2026-08-23

- Published the strict `dagwright.io/v1alpha1` DataProduct contract and JSON Schema.
- Added deterministic JSON/YAML parsing, normalization, canonical IR, stable IDs, graph validation,
  schema hooks, canonical serialization, and SHA-256 digests.
- Added the generation-only Airflow 3 adapter, capability document, fail-closed DAG, artifact
  metadata, and lineage.
- Added `dagwright validate`, `dagwright compile`, and `dagwright explain`.
- Added the customer analytics reference workflow and exact end-to-end golden bundle.

### Corrected v0.1 scope — 2026-08-24

- Standardized the entire compiler on Python 3.12+, uv, Pydantic v2, Typer, SQLGlot, NetworkX,
  Jinja2, pytest/Hypothesis, Ruff, mypy, and Pyright.
- Added deterministic planning, Spark/Iceberg generation, static artifact validation, targeted
  compilation, manifest inspection, and a database-free Docker Compose demonstration.
- Explicitly postponed PostgreSQL persistence, agents/LLMs, MCP, UI, additional orchestrators,
  distributed infrastructure, microservices, and Rust.
