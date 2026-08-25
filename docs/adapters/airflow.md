# Airflow 3 adapter

The Airflow 3 adapter is a deterministic, generation-only adapter for the supported
`dagwright.io/v1alpha1` subset. Its machine-readable capability document is
[`adapters/airflow/capabilities-v1alpha1.json`](../../adapters/airflow/capabilities-v1alpha1.json).

```python
from dagwright.adapters.airflow import Airflow3Adapter

bundle = Airflow3Adapter().generate(compilation.ir)
bundle.artifact.content  # importable Airflow 3 Python
bundle.manifest_bytes  # deterministic metadata and lineage JSON
```

Generation performs no execution or deployment. The emitted tasks fail closed until later workload
adapters bind executable implementations. Call `validate()` to inspect all capability violations or
`generate()` to reject them as one `UnsupportedSemanticsError`.
