# DAGwright

DAGwright is an open-source, engine-neutral agentic compiler and control plane for data
engineering. v0.2 is a Python 3.12 compiler that turns a strict `dagwright.io/v1alpha1`
DataProduct contract into canonical IR and deterministic Airflow 3 plus Spark/Iceberg artifacts.
Local compilation requires no database and does not execute or deploy data products.

## Development

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
make install
make verify
uv run dagwright version
uv run dagwright doctor
uv run dagwright validate examples/customer-analytics/dataproduct.yaml
uv run dagwright plan examples/customer-analytics/dataproduct.yaml
uv run dagwright compile examples/customer-analytics/dataproduct.yaml --target airflow \
  -o build/customer-airflow
uv run dagwright compile examples/customer-analytics/dataproduct.yaml \
  -o build/customer-analytics
uv run dagwright inspect build/customer-analytics/manifest.json
uv run dagwright compile examples/customer-analytics/dataproduct.yaml \
  --overlay examples/customer-analytics/development.overlay.yaml \
  --target spark -o build/customer-development
```

For the database-free container demonstration, run `docker compose run --rm compiler`; it writes
the deterministic bundle to `build/compose`.

## Local Spark/Iceberg verification

With Java 17 available, run the first v0.2 execution checkpoint:

```sh
make verify-reference
make verify-reference-failure
make verify-wheel
make release-candidate
```

Or run the public suite workflow directly:

```sh
uv sync --extra execution
uv run dagwright verify examples/customer-analytics/dataproduct.yaml \
  --suite examples/customer-analytics/verification.yaml \
  --output build/verification
```

This installs the locked optional PySpark 3.5 runtime, loads the official Iceberg Spark runtime JAR,
executes the generated customer-analytics transformation twice, reads the local Iceberg table back,
checks rows, schema, quality rules and negative controls, proves replace-output idempotency, and
writes deterministic evidence to `build/reference-execution/evidence.json`. PostgreSQL is not used.
The failure target proves that an intentional row mismatch exits nonzero while retaining strict
diagnostic evidence.

`make release-candidate` builds the wheel and source archive twice, rejects byte differences,
smoke-tests the wheel, and writes SHA-512 checksums, a CycloneDX runtime SBOM, and a dependency
license inventory under `build/release/`. It does not tag, sign, upload, or publish anything.

The generated contract schema is [schemas/dataproduct-v1alpha1.json](schemas/dataproduct-v1alpha1.json),
and the validated customer example is
[examples/contracts/customer-360.json](examples/contracts/customer-360.json). Run `make schema`
after changing contract models; `make verify` rejects stale schema output.

The deterministic compiler checkpoint can parse JSON or YAML and produce normalized contract and
canonical IR bytes with SHA-256 digests:

```python
from pathlib import Path

from dagwright.compiler import compile_contract
from dagwright.contracts import parse_contract_file

result = compile_contract(parse_contract_file(Path("examples/contracts/customer-360.json")))
print(result.contract_digest, result.ir_digest)
```

SQLGlot validates referenced Spark SQL, NetworkX produces the canonical topological plan, and
Jinja2 renders generated Python. Every generated Python file and manifest digest is checked before
the bundle is written.

Repeatable `--overlay` options apply explicit, replacement-only environment patches before every
compiler gate. Conflicting or invalid JSON-pointer patches fail before artifacts are written.

The first generation-only adapter emits an importable Airflow 3 DAG and artifact manifest:

```python
from dagwright.adapters.airflow import Airflow3Adapter

bundle = Airflow3Adapter().generate(result.ir)
```

The generated DAG is a fail-closed orchestration scaffold. DAGwright does not execute or deploy it,
and its tasks refuse to run until workload implementations are bound explicitly.

See [CONTRIBUTING.md](CONTRIBUTING.md), [PLAN.md](PLAN.md), the
[v0.1 guide](docs/v0.1.md), the
[v0.2 checkpoint 3 guide](docs/v0.2-checkpoint-3.md), the
[v0.2 checkpoint 4 guide](docs/v0.2-checkpoint-4.md), the
[v0.2 release-candidate guide](docs/v0.2-release-candidate.md), and the
[architecture plan](docs/DAGwright_Architecture_and_Implementation_Plan.md).

## License

Licensed under the Apache License, Version 2.0. DAGwright is not an Apache Software Foundation
project and must not be described as one unless accepted by the ASF.
