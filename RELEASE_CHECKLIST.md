# Release checklist

This checklist is a project practice, not an ASF release process. DAGwright is not currently an
Apache Software Foundation project.

- [ ] Scope matches the milestone and all exit conditions are documented in `PLAN.md`.
- [ ] Public schemas, manifests, golden files, changelog, compatibility notes, and docs are current.
- [ ] `uv lock --check`, `make verify`, `make verify-wheel`, and applicable real-engine checks pass.
- [ ] The source archive and wheel install cleanly and contain `LICENSE`, `NOTICE`, and schemas.
- [ ] Dependency licenses and the vulnerability audit are reviewed.
- [ ] Every commit has provenance and required DCO sign-off; third-party notices are complete.
- [ ] A release candidate tag is immutable and its commit, artifacts, and SHA-512 digests are named.
- [ ] At least two maintainers review the candidate; objections and resolutions are public.
- [ ] Artifacts are signed when project signing infrastructure is available.
- [ ] The release notes clearly state experimental features and unsupported production use.
- [ ] After approval, publish artifacts, create the final tag, and verify all download links.
