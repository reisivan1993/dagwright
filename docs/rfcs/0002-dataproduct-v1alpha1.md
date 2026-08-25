# RFC-0002: DataProduct v1alpha1 contract

- Status: Accepted
- Authors: DAGwright contributors
- Created: 2026-08-22

## Summary

Define the first versioned, engine-neutral `DataProduct` contract at
`dagwright.io/v1alpha1`. The Pydantic v2 domain model is authoritative for Python callers and a
deterministically generated JSON Schema is published for independent implementations.

## Contract boundary

The root identifies `apiVersion`, `kind`, and a semantic `version`, then declares metadata,
sources, assets, transformations, operational contracts, execution roles, and governance. Quality
rules are deterministic expectations. Anomaly rules declare signals but do not prescribe an
anomaly-detection implementation. Execution fields name engine roles without generating or
deploying engine artifacts.

All declared fields use lower camel case in serialized contracts. Models are strict and immutable:
values are not coerced and unknown properties fail validation. A property beginning with a valid,
lowercase `x-` namespace is preserved as JSON data at any object boundary. This allows independent
experimentation without weakening validation for standard fields.

## Compatibility

`v1alpha1` may change incompatibly before promotion. The `apiVersion` selects schema compatibility;
the separate semantic `version` identifies the user-owned contract revision. Unknown standard
fields remain errors so a contract cannot silently acquire semantics an older implementation does
not understand.

## Publication and verification

`schemas/dataproduct-v1alpha1.json` uses JSON Schema Draft 2020-12. It is generated from the models
with sorted keys and checked for byte-for-byte freshness in `make verify`. Examples are validated
against both Pydantic and the published schema. Semantic constraints that JSON Schema cannot
express, such as ordering two independently supplied numeric fields, remain Pydantic validation
rules and are covered by fixture tests.

## Deferred work

Parsing with source locations, normalization, reference resolution, overlays, canonical IR,
adapters, and artifact generation are separate v0.1 checkpoints and are not part of this RFC.
