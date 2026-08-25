.PHONY: install format lint typecheck test audit schema schema-check adapters-check golden verify verify-reference verify-reference-failure verify-wheel release-candidate

install:
	uv sync --locked --all-groups

format:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy
	uv run pyright

test:
	uv run pytest

audit:
	uv run pip-audit --cache-dir .cache/pip-audit --local --skip-editable

schema:
	uv run python -m dagwright.contracts.schema
	uv run python -m dagwright.verification.schema
	uv run python -m dagwright.overlay_schema

schema-check:
	uv run python -m dagwright.contracts.schema --check
	uv run python -m dagwright.verification.schema --check
	uv run python -m dagwright.overlay_schema --check

adapters-check:
	uv run python -m dagwright.adapters.airflow --check

golden:
	uv run python tools/update_compiler_golden.py
	uv run python tools/update_airflow_golden.py
	uv run python tools/update_v01_golden.py
	uv run python tools/update_overlay_golden.py

verify: lint typecheck test schema-check adapters-check audit

verify-reference: golden
	mkdir -p build/reference-execution
	uv run --python 3.12 --extra execution spark-submit \
		--master 'local[2]' \
		--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.11.0 \
		--conf spark.jars.ivy=/tmp/dagwright-ivy \
		--conf spark.ui.enabled=false \
		--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
		--conf spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog \
		--conf spark.sql.catalog.local.type=hadoop \
		--conf spark.sql.catalog.local.warehouse=file://$(CURDIR)/build/reference-execution/warehouse \
		--conf spark.sql.defaultCatalog=local \
		tools/run_reference_pipeline.py \
		--contract tests/golden/e2e/customer-analytics/contract.normalized.json \
		--generated tests/golden/e2e/customer-analytics/spark/build_customer_engagement.py \
		--suite examples/customer-analytics/verification.yaml \
		--evidence build/reference-execution/evidence.json \
		--warehouse build/reference-execution/warehouse
	cmp build/reference-execution/evidence.json tests/golden/execution/customer-analytics.evidence.json
	uv run dagwright inspect-evidence build/reference-execution/evidence.json

verify-reference-failure: golden
	mkdir -p build/reference-failure
	! uv run --python 3.12 --extra execution spark-submit \
		--master 'local[2]' \
		--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.11.0 \
		--conf spark.jars.ivy=/tmp/dagwright-ivy \
		--conf spark.ui.enabled=false \
		--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
		--conf spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog \
		--conf spark.sql.catalog.local.type=hadoop \
		--conf spark.sql.catalog.local.warehouse=file://$(CURDIR)/build/reference-failure/warehouse \
		--conf spark.sql.defaultCatalog=local \
		tools/run_reference_pipeline.py \
		--contract tests/golden/e2e/customer-analytics/contract.normalized.json \
		--generated tests/golden/e2e/customer-analytics/spark/build_customer_engagement.py \
		--suite examples/customer-analytics/verification-failure.yaml \
		--evidence build/reference-failure/evidence.json \
		--warehouse build/reference-failure/warehouse
	! uv run dagwright inspect-evidence build/reference-failure/evidence.json
	uv run python -c "from pathlib import Path; from dagwright.evidence import read_execution_evidence; e=read_execution_evidence(Path('build/reference-failure/evidence.json')); assert e.failure_reasons == ('rows_mismatch',)"

verify-wheel:
	uv build
	uv run python tools/verify_wheel.py dist

release-candidate: verify
	uv run python tools/build_release_candidate.py
