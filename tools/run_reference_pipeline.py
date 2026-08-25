"""Execute a generated Spark/Iceberg workload from a VerificationSuite."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
from pathlib import Path
from typing import Any

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as fn


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalized_rows(frame: DataFrame, order_by: list[str]) -> list[dict[str, Any]]:
    rows = [row.asDict(recursive=True) for row in frame.orderBy(*order_by).collect()]
    return json.loads(json.dumps(rows, default=str))


def load_generated(path: Path) -> tuple[str, str, str, str]:
    module = runpy.run_path(str(path), run_name="dagwright_generated_verification")
    return (
        module["SQL"],
        module["OUTPUT_TABLE"],
        module["DAGWRIGHT_CONTRACT_DIGEST"],
        module["DAGWRIGHT_IR_DIGEST"],
    )


def quality_results(
    frame: DataFrame, contract: dict[str, Any], asset: str, frames: dict[str, DataFrame]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in contract["contracts"]["quality"]:
        if rule["asset"] != asset:
            continue
        fields = rule["fields"]
        if rule["type"] == "not_null":
            condition = fn.lit(False)
            for field in fields:
                condition = condition | fn.col(field).isNull()
            failures = frame.filter(condition).count()
        elif rule["type"] == "unique":
            failures = frame.groupBy(*fields).count().filter(fn.col("count") > 1).count()
        elif rule["type"] == "accepted_values":
            failures = frame.filter(~fn.col(fields[0]).isin(rule["values"])).count()
        elif rule["type"] == "expression":
            failures = frame.filter(
                ~fn.coalesce(fn.expr(rule["expression"]), fn.lit(False))
            ).count()
        elif rule["type"] == "referential_integrity":
            reference_asset, reference_field = rule["reference"].split(".", 1)
            reference = frames[reference_asset].select(
                fn.col(reference_field).alias("__dagwright_reference")
            )
            failures = frame.join(
                reference, frame[fields[0]] == reference["__dagwright_reference"], "left_anti"
            ).count()
        else:
            raise RuntimeError(f"unsupported quality rule: {rule['type']}")
        results.append(
            {
                "asset": rule["asset"],
                "failureCount": failures,
                "passed": failures == 0,
                "ruleId": rule["id"],
                "ruleType": rule["type"],
            }
        )
    return sorted(results, key=lambda item: item["ruleId"])


def _load_fixtures(
    spark: SparkSession, root: Path, fixtures: list[dict[str, str]]
) -> dict[str, DataFrame]:
    frames: dict[str, DataFrame] = {}
    for fixture in fixtures:
        frame = spark.read.json(str(root / fixture["path"]))
        frame.createOrReplaceTempView(fixture["view"])
        frames[fixture["view"]] = frame
    return frames


def execute(args: argparse.Namespace) -> dict[str, Any]:
    contract = json.loads(args.contract.read_text())
    suite = yaml.safe_load(args.suite.read_text())
    sql, output_name, contract_digest, ir_digest = load_generated(args.generated)
    expected_rows = json.loads((args.suite.parent / suite["expected"]["rows"]).read_text())
    expected_schema = json.loads((args.suite.parent / suite["expected"]["schema"]).read_text())
    order_by = suite["expected"]["orderBy"]
    table = f"local.dagwright.{output_name}"
    spark = SparkSession.builder.appName("dagwright-local-verification").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS local.dagwright")
        spark.sql(f"DROP TABLE IF EXISTS {table}")
        frames = _load_fixtures(spark, args.suite.parent, suite["fixtures"])
        runs: list[dict[str, Any]] = []
        for attempt in range(1, suite["attempts"] + 1):
            spark.sql(sql).writeTo(table).using("iceberg").createOrReplace()
            rows = normalized_rows(spark.table(table), order_by)
            runs.append({"attempt": attempt, "outputDigest": digest(rows), "rowCount": len(rows)})
        output = spark.table(table)
        actual_rows = normalized_rows(output, order_by)
        actual_schema = [
            {"name": field.name, "nullable": field.nullable, "type": field.dataType.simpleString()}
            for field in output.schema.fields
        ]
        quality = quality_results(output, contract, output_name, frames)
        negative_quality: list[dict[str, Any]] = []
        negative_controls: list[dict[str, Any]] = []
        input_paths = {item["path"] for item in suite["fixtures"]}
        for control in suite["negativeControls"]:
            frames = _load_fixtures(spark, args.suite.parent, suite["fixtures"])
            control_frames = _load_fixtures(spark, args.suite.parent, control["fixtures"])
            input_paths.update(item["path"] for item in control["fixtures"])
            control_quality = quality_results(
                spark.sql(sql), contract, output_name, {**frames, **control_frames}
            )
            negative_quality.extend(control_quality)
            actual_failures = sorted(
                item["ruleId"] for item in control_quality if item["failureCount"] > 0
            )
            expected_failures = sorted(control["expectedFailures"])
            negative_controls.append(
                {
                    "actualFailures": actual_failures,
                    "expectedFailures": expected_failures,
                    "name": control["name"],
                    "passed": actual_failures == expected_failures,
                    "quality": control_quality,
                }
            )
        negative_control_passed = bool(negative_controls) and all(
            item["passed"] for item in negative_controls
        )
        inputs = [
            {
                "path": path,
                "sha256": hashlib.sha256((args.suite.parent / path).read_bytes()).hexdigest(),
            }
            for path in sorted(input_paths)
        ]
        expected_digest = digest(expected_rows)
        rows_passed = actual_rows == expected_rows
        schema_passed = actual_schema == expected_schema
        idempotency_passed = len({(run["rowCount"], run["outputDigest"]) for run in runs}) == 1
        quality_passed = all(item["passed"] for item in quality)
        failure_reasons = sorted(
            reason
            for reason, passed in (
                ("rows_mismatch", rows_passed),
                ("schema_mismatch", schema_passed),
                ("quality_failed", quality_passed),
                ("negative_control_failed", negative_control_passed),
                ("idempotency_failed", idempotency_passed),
            )
            if not passed
        )
        verification_passed = (
            rows_passed
            and schema_passed
            and quality_passed
            and negative_control_passed
            and idempotency_passed
        )
        return {
            "apiVersion": "dagwright.io/execution-evidence/v1alpha1",
            "contractDigest": contract_digest,
            "dataProductId": f"urn:dagwright:{contract['metadata']['name']}:dataproduct",
            "engine": "apache-spark-3.5",
            "expectedOutputDigest": expected_digest,
            "idempotencyMode": contract["execution"]["idempotency"]["mode"],
            "idempotencyPassed": idempotency_passed,
            "failureReasons": failure_reasons,
            "inputs": inputs,
            "irDigest": ir_digest,
            "quality": quality,
            "qualityNegativeControl": negative_quality,
            "qualityNegativeControlPassed": negative_control_passed,
            "negativeControls": negative_controls,
            "rowsPassed": rows_passed,
            "runs": runs,
            "schema": actual_schema,
            "schemaPassed": schema_passed,
            "table": table,
            "tableFormat": "apache-iceberg",
            "verificationPassed": verification_passed,
        }
    finally:
        spark.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--warehouse", type=Path, required=True)
    args = parser.parse_args()
    table_directory = args.warehouse / "dagwright"
    if table_directory.exists():
        shutil.rmtree(table_directory)
    evidence = execute(args)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence_bytes = canonical_bytes(evidence) + b"\n"
    args.evidence.write_bytes(evidence_bytes)
    print(f"evidence sha256:{hashlib.sha256(evidence_bytes).hexdigest()}")
    return 0 if evidence["verificationPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
