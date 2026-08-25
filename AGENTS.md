# Contributor instructions

## Commands

- Install: `make install`
- Verify everything: `make verify`
- Format: `make format`
- Test: `make test`
- Run the CLI: `uv run dagwright doctor`
- Exercise v0.1: `uv run dagwright plan examples/customer-analytics/dataproduct.yaml`
- Exercise the real reference pipeline: `make verify-reference` (Java 17; downloads Spark/Iceberg).
- Exercise a suite: `uv run --extra execution dagwright verify PRODUCT --suite SUITE --output DIR`.

## Architecture rules

- Require Python 3.12+ and manage dependencies with `uv`; commit `uv.lock`.
- Keep a CLI-first modular monolith under `src/dagwright`; separate modules by domain responsibility.
- Use Pydantic v2 at external and domain boundaries and Typer for CLI commands.
- Use SQLGlot for SQL validation, NetworkX for DAG planning, and Jinja2 for generated code.
- Keep the deterministic core engine-neutral. Do not add engine integrations to the core package.
- Add typed tests for behavior; use Hypothesis for invariants where it adds value.
- Keep formatting, Ruff, strict mypy, Pyright, pytest, and dependency audit green.
- Keep local compilation self-contained; PostgreSQL is never a compiler dependency.
- Keep verification suites versioned, deterministic, path-confined, and separate from contracts.
- Do not add Rust, LLM/agent, MCP, web UI, microservice, or distributed-runtime code in v0.1.
- Record durable architecture choices in `docs/adr` and proposals in `docs/rfcs`.
- Do not implement roadmap work beyond the active milestone.
