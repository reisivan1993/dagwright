# RFC-0001: Project foundation

- Status: Accepted
- Authors: DAGwright contributors
- Created: 2026-08-22

## Summary

Establish DAGwright as an open-source, engine-neutral agentic compiler and control plane for data
engineering. Begin with a CLI-first Python modular monolith and public, reviewable governance.

## Scope

v0.0 contains repository conventions, licensing, RFCs and ADRs, verification tooling, CI, and a
minimal `version`/`doctor` CLI. It deliberately contains no `DataProduct` compiler, engine adapter,
or distributed runtime. v0.1 introduces the deterministic contract-to-artifact compiler through
separately reviewable work listed in `PLAN.md`.

## Compatibility

The package and CLI name are `dagwright`; the future API group is `dagwright.io`. There is no public
contract or API compatibility promise at v0.0.

## Governance and licensing

Source is Apache-2.0 licensed, contributions use DCO sign-off, and decisions occur in public RFCs,
ADRs, issues, and pull requests. DAGwright is independent and does not claim ASF project status.
