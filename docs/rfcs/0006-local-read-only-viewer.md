# RFC-0006: Local read-only Viewer

- Status: Accepted
- Date: 2026-08-25

## Summary

Add an optional `dagwright ui PRODUCT` command that presents existing deterministic compilation
output in a local browser. The Viewer is part of the Python modular monolith and is downstream of
the compiler; it does not define contracts, IR, planning, or adapter behavior.

## Decision

The command compiles one explicit local DataProduct and any explicit overlays before opening a
standard-library HTTP server bound to `127.0.0.1`. The server exposes packaged static resources and
one immutable in-memory JSON snapshot. The snapshot contains graph, plan, canonical contract, IR,
manifest, digest, and generated-artifact views.

The first checkpoint has no editing, uploads, arbitrary file reads, write endpoints, remote bind,
authentication, persistence, execution, or deployment. Browser code uses no CDN and renders all
contract-derived values through text-only DOM APIs.

## Consequences

- Contributors can understand compilation output without learning every JSON artifact first.
- CLI and Python compiler behavior remain authoritative and independently usable.
- The installed package grows by small static assets but gains no runtime dependency.
- A production UI or control plane would require a separate RFC and threat model.
