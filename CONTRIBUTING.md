# Contributing to DAGwright

Thank you for helping build DAGwright. Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Before opening a change

Use an issue or RFC for changes that affect public contracts, architecture, security, governance,
or compatibility. Small fixes may go directly to a pull request. The process is documented in
[`docs/rfcs/README.md`](docs/rfcs/README.md).

## Development workflow

1. Install Python 3.12+ and `uv`.
2. Run `make install`.
3. Create a focused branch and add tests with the change.
4. Run `make verify` before opening a pull request.
5. Run `make verify-wheel` for packaging or CLI changes and real-engine targets for execution changes.
6. Explain user impact, tests, and compatibility considerations in the pull request.

Contributions must include a Developer Certificate of Origin sign-off (`git commit -s`). By signing
off, contributors certify the statement in [DCO.md](DCO.md).

The project uses Apache License 2.0. Unless explicitly stated otherwise, submitted contributions
are provided under that license.

Releases follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Apache-style readiness gaps are
tracked transparently in [ASF_READINESS.md](ASF_READINESS.md); DAGwright is not an ASF project.
