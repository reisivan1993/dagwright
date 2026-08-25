# RFC-0005: Deterministic environment overlays

- Status: Accepted
- Date: 2026-08-25

## Problem

Teams need environment-specific schedules, resource hints, secret references, and metadata without
copying an entire DataProduct. Unspecified merge behavior would make compilation order-dependent
and make review artifacts difficult to reproduce.

## Decision

DAGwright defines `dagwright.io/v1alpha1` `DataProductOverlay`. Each named overlay contains one or
more JSON-pointer replacement patches. Patches may replace existing values only; they cannot add or
delete fields. The fully overlaid document must pass the normal strict DataProduct validation and
all compiler gates.

Within and across overlays, duplicate paths and ancestor/descendant paths are conflicts. Overlay
names must be unique. Disjoint patches are applied after sorting by overlay name and pointer, making
results independent of CLI argument order. Diagnostics identify both owners and paths for conflicts.
Contract API version, kind, semantic version, and DataProduct name are immutable under overlays.

The normalized contract and its digest represent the effective configuration. Source contracts and
overlay documents remain separate review inputs; overlays never mutate the source file.

## CLI

`--overlay FILE` is repeatable on `validate`, `plan`, `compile`, `explain`, and `verify`:

```sh
dagwright compile product.yaml --overlay development.overlay.yaml --target spark
```

## Consequences

Replacement-only semantics are intentionally less expressive than strategic merge patches, but are
small, deterministic, and easy to audit. Adding fields, list insertion, deletion, conditional
patches, secret resolution, deployment history, and environment discovery remain out of scope.
