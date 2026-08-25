# DAGwright implementation plan

Each checkbox is intended to be one reviewable commit. The corrected v0.1 milestone completed on
2026-08-24 after its Airflow/Spark/Iceberg exit condition passed.

## v0.0 — Repository and RFC foundation

- [x] Establish the Python 3.12 `src` layout and package metadata with `uv`.
- [x] Add Apache-2.0 licensing, notice, conduct, security, governance, and contribution files.
- [x] Document contributor commands and architectural boundaries in `AGENTS.md`.
- [x] Publish the RFC process and RFC-0001 project scope.
- [x] Record the CLI-first modular-monolith choice in ADR-0001.
- [x] Configure Ruff formatting/linting, strict mypy, pytest, and Hypothesis.
- [x] Add the `dagwright version` command and smoke tests.
- [x] Add the `dagwright doctor` environment check and property tests.
- [x] Add dependency auditing and a one-command `make verify` target.
- [x] Add CI that installs from the lockfile and runs `make verify`.
- [x] Produce and validate the committed `uv.lock` file.

Exit condition: a clean checkout installs; the CLI runs; lint, types, tests, and dependency audit
pass; CI and repository conventions exist; v0.1 work is explicit.

## v0.1 — Deterministic Python compiler (complete 2026-08-24)

Objective: build a deterministic, Python-based compiler that converts a validated DataProduct
contract into deployable Airflow 3 and Spark/Iceberg artifacts.

- [x] Write an RFC for `dagwright.io/v1alpha1` `DataProduct` scope and compatibility rules.
- [x] Define the strict Pydantic v2 contract models and publish matching JSON Schema.
- [x] Implement YAML/JSON parsing with actionable source-location errors.
- [x] Normalize contracts deterministically and prove normalization idempotence.
- [x] Resolve local references and reject cycles or missing targets.
- [x] Define the engine-neutral canonical IR and stable node identifiers.
- [x] Compile normalized contracts into IR without engine-specific dependencies.
- [x] Validate DAG acyclicity and resolved edge references.
- [x] Validate Airflow-supported execution semantics through adapter capabilities.
- [x] Compute versioned contract and IR digests from canonical serialization.
- [x] Provide engine-neutral schema compatibility hooks.
- [x] Specify the generation adapter capability interface and capability-negotiation errors.
- [x] Generate a minimal Airflow 3 DAG from the same IR fixture.
- [x] Add golden tests proving reproducible contract, IR, manifest, and artifact output.
- [x] Add checkpoint golden tests for normalized contract and canonical IR output.
- [x] Add exact golden tests for the Airflow DAG, artifact manifest, and lineage.
- [x] Add `validate`, `compile`, and `explain` commands with human-readable diagnostics.
- [x] Emit a top-level manifest with SHA-256 and size for every review artifact.
- [x] Add and document the customer analytics hand-authored reference workflow.
- [x] Validate referenced SQL deterministically with SQLGlot.
- [x] Plan and validate canonical graphs with NetworkX.
- [x] Render Airflow and Spark code through deterministic Jinja2 templates.
- [x] Generate Spark jobs and Iceberg target metadata.
- [x] Add `plan`, targeted `compile`, and manifest `inspect` CLI workflows.
- [x] Statically validate generated Python and every manifest digest.
- [x] Add a database-free Docker Compose compilation demonstration.
- [x] Cover the complete Airflow/Spark/Iceberg bundle with integration and golden tests.

Exit condition: `dagwright compile product.yaml` works without PostgreSQL and reproducibly emits a
statically validated Airflow 3 and Spark/Iceberg bundle.

## Post-v0.1 deterministic backlog

These items remain explicit and are not part of the completed v0.1 release profile:

- [ ] Define and apply deterministic environment overlays with conflict diagnostics.
- [ ] Add PostgreSQL-backed operational history, approvals, deployments, and audit records without
  making the compiler depend on PostgreSQL.
- [ ] Extend capability negotiation for each additional adapter as it is introduced.

## v0.2 — Local execution and verification

### Checkpoint 1 — Customer analytics reference execution

- [x] Add deterministic customer, event, expected-output, expected-schema, and negative-control fixtures.
- [x] Run the generated SQL with Apache Spark 3.5 against a local Hadoop-backed Iceberg catalog.
- [x] Read the generated Iceberg table back and compare exact rows and schema.
- [x] Execute declared not-null and uniqueness rules, including failing negative controls.
- [x] Execute the replace-output write twice and prove stable row count and output digest.
- [x] Emit and strictly validate deterministic `dagwright.io/execution-evidence/v1alpha1` evidence.
- [x] Add `make verify-reference`, `dagwright inspect-evidence`, golden tests, and an opt-in real-engine integration test.

Exit condition: the customer analytics generated Spark workload runs twice against local Iceberg;
rows, schema, quality, negative controls, and idempotency pass; the evidence file matches its golden
bytes. No database or control-plane service is required.

### Checkpoint 2 — Reusable verification workflow

- [x] Define a strict, versioned `VerificationSuite` YAML/JSON contract with safe fixture paths.
- [x] Drive the Spark/Iceberg verifier from the suite instead of customer-specific arguments.
- [x] Add `dagwright verify PRODUCT --suite SUITE` as the compile-and-execute entry point.
- [x] Implement every v0.1 quality-rule evaluator and report deterministic evidence.
- [x] Add suite parsing, failure-path, CLI, real-engine, and golden tests.
- [x] Document the authoring and local verification workflow and run every project gate.

Exit condition: one CLI command compiles a DataProduct, executes a declared verification suite on
local Spark/Iceberg, and emits strict deterministic evidence; both success and controlled failure
paths are tested.
