# Customer analytics reference example

This example is the v0.1 hand-authored contract-to-review-artifacts workflow. It declares two batch
PostgreSQL sources, three Iceberg-shaped assets, one SQL transformation, quality gates, an anomaly
signal, operational expectations, and Airflow orchestration.

```sh
uv run dagwright validate examples/customer-analytics/dataproduct.yaml
uv run dagwright explain examples/customer-analytics/dataproduct.yaml
uv run dagwright compile examples/customer-analytics/dataproduct.yaml \
  --output build/customer-analytics
```

The output is deterministic and review-only. The generated Airflow tasks fail closed because v0.1
does not bind or execute the reference SQL. Inspect `manifest.json` first: it records every emitted
file, digest, compiler/adapter version, and input contract/IR digest.

`verification.yaml` binds deterministic fixtures and expected output to the generated transformation.
With Java 17 installed, execute it locally with:

```sh
uv run --extra execution dagwright verify examples/customer-analytics/dataproduct.yaml \
  --suite examples/customer-analytics/verification.yaml \
  --output build/customer-analytics-verification
```

The successful result includes a compiled bundle, local Iceberg warehouse, and strict
`evidence.json`; no PostgreSQL service is required.
