import ast
import json
from pathlib import Path
from typing import Any, cast

from hypothesis import given
from hypothesis import strategies as st

from dagwright.adapters.spark import SparkIcebergAdapter
from dagwright.compiler import build_execution_plan, compile_contract, load_validated_sql
from dagwright.contracts import parse_contract_file

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "examples/customer-analytics/dataproduct.yaml"


def compilation_and_sql() -> tuple[Any, dict[str, str]]:
    contract = parse_contract_file(CONTRACT)
    return compile_contract(contract), load_validated_sql(contract, CONTRACT.parent)


def test_networkx_plan_is_stable_and_respects_every_edge() -> None:
    compilation, _ = compilation_and_sql()

    first = build_execution_plan(compilation.ir)
    second = build_execution_plan(compilation.ir)
    positions = {step.stable_id: step.position for step in first.steps}

    assert first == second
    assert len(first.steps) == len(compilation.ir.nodes)
    assert all(positions[edge.source] < positions[edge.target] for edge in compilation.ir.edges)


@given(st.integers(min_value=1, max_value=20))
def test_planning_is_independent_of_ir_node_rotation(offset: int) -> None:
    compilation, _ = compilation_and_sql()
    nodes = compilation.ir.nodes
    split = offset % len(nodes)
    rotated = compilation.ir.model_copy(update={"nodes": (*nodes[split:], *nodes[:split])})

    assert build_execution_plan(rotated) == build_execution_plan(compilation.ir)


def test_spark_iceberg_generation_is_static_and_deterministic() -> None:
    compilation, sql = compilation_and_sql()
    adapter = SparkIcebergAdapter()

    first = adapter.generate(compilation.ir, sql)
    second = adapter.generate(compilation.ir, sql)

    assert first == second
    spark_job = next(item for item in first.artifacts if item.role == "spark_job")
    ast.parse(spark_job.content)
    assert b"SparkSession" in spark_job.content
    iceberg = next(item for item in first.artifacts if item.role == "iceberg_metadata")
    document = cast(dict[str, Any], json.loads(iceberg.content))
    assert document["catalog"] == "iceberg-rest"
    assert [table["name"] for table in document["tables"]] == [
        "customer_engagement",
        "raw_customer_events",
        "raw_customers",
    ]
    assert all(
        metadata.sha256
        == next(item.sha256 for item in first.artifacts if item.path == metadata.path)
        for metadata in first.manifest.artifacts
    )
