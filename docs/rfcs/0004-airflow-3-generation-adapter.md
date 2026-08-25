# RFC-0004: Airflow 3 generation adapter

- Status: Accepted
- Authors: DAGwright contributors
- Created: 2026-08-23

## Summary

Add the first generation-only adapter for Apache Airflow 3. The adapter consumes canonical
`dagwright.ir/v1alpha1`, validates its requested semantics against a published capability document,
and emits a deterministic Python DAG plus a canonical artifact manifest and lineage map.

## Safety boundary

The adapter exposes only capabilities, validation, and generation. It has no execute, apply, deploy,
observe, cancel, or rollback method and does not import Airflow while generating. Generated task
bodies are fail-closed scaffolds: importing the file constructs a DAG, but a task run raises until a
later workload or quality implementation is explicitly bound. This prevents an incomplete no-op
pipeline from reporting false success.

## Supported v1alpha1 subset

- Airflow 3 through the public `airflow.sdk` `dag` and `task` decorators;
- manual, valid five-field cron, and standard preset schedules;
- source, asset, transformation, quality, and anomaly nodes;
- every canonical dependency edge;
- fail-closed failure policy and integer `maxAttempts >= 1` retry policy;
- batch sources and CDC delegated explicitly to the source implementation;
- quality nodes represented as terminal fail-closed gates;
- freshness, volume, delivery, late-data, and watermark contracts preserved verbatim in the
  manifest and delegated explicitly to later workload adapters;
- resource hints and execution roles preserved in the input IR and its digest.

Streaming sources are rejected. The adapter claims no exactly-once scope, checkpointing, schema
evolution, rollback, deployment, or cost visibility. Unsupported requests return all stable,
path-addressed capability violations and generate no artifact.

## Determinism and provenance

Tasks and edges are ordered by stable identifiers. Task IDs derive from node kind and name. Airflow
retry count is `maxAttempts - 1`, preserving the difference between attempts and retries. The
manifest records adapter/target versions, exact source hash and size, input IR and contract digests,
task metadata, delegated operational contracts, and stable-ID lineage for every edge. No timestamps
or machine-local paths enter output.

## Compatibility verification

Golden tests compare exact DAG and manifest bytes. Import tests load the generated customer DAG with
the Airflow 3.3.1 Task SDK and inspect schedule, retries, task IDs, dependencies, and fail-closed
quality behavior. Capability publication is checked byte-for-byte by `make verify`.

## Deferred work

Workload binding, Spark or Iceberg artifacts, Airflow deployment/observation, rollback, and other
orchestrators are separate checkpoints.
