# RFC-0003: Deterministic normalization and canonical pipeline IR

- Status: Accepted
- Authors: DAGwright contributors
- Created: 2026-08-23

## Summary

Define the deterministic boundary between a valid `DataProduct` contract and DAGwright's first
engine-neutral pipeline intermediate representation. The boundary parses JSON or YAML, resolves
defaults and local references, constructs a validated dependency graph, and emits canonical bytes
and SHA-256 digests for both the normalized contract and IR.

## Parsing and normalization

JSON and YAML parsers reject duplicate keys, non-object roots, syntax errors, and unsupported file
extensions. Errors identify the source and, when the parser provides them, line and column. Model
validation errors identify JSON-style object paths.

Normalization materializes every Pydantic default and nullable field. Collections whose declaration
order has no semantic meaning—sources, assets, transformations, quality rules, and anomaly rules—are
sorted by their unique name or ID. Potentially meaningful lists such as primary keys and ordered
transformation references retain their order. Extension values are preserved.

Canonical serialization is UTF-8 JSON with sorted object keys, no insignificant whitespace, no NaN
values, aliases matching the public contract, and all resolved defaults. The digest is the lowercase
hexadecimal SHA-256 of exactly those bytes.

## Reference and graph semantics

- The prefix of `asset.source` resolves to a declared source.
- Asset inputs and transformation inputs/outputs resolve to declared assets.
- Asset transformation IDs resolve to declared transformations whose output is that asset.
- Quality and anomaly assets, and the asset prefix of quality references, must exist.

The IR converts all resolved references to stable URNs rooted at the DataProduct name. It contains
source, asset, transformation, quality, and anomaly nodes plus sorted, stable dependency edges.
Cycles and missing references fail before an IR is returned. Stable IDs do not include declaration
position or contract version, so reordering or revising the same logical object does not rename it.

## Schema compatibility

Compiler callers may register typed compatibility hooks. A hook receives each data-carrying upstream
and downstream node and returns deterministic rejection messages. The core provides the hook point
and optional schema slots but does not infer schemas or depend on a compute engine in this checkpoint.

## Deferred work

Environment overlays, schema discovery, adapter capability negotiation, engine artifacts,
orchestrator generators, and deployment are outside this RFC.
