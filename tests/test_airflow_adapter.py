import builtins
import importlib.util
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from dagwright.adapters.airflow import Airflow3Adapter, capability_bytes
from dagwright.adapters.base import UnsupportedSemanticsError
from dagwright.compiler import compile_contract
from dagwright.compiler.canonical import canonical_digest
from dagwright.compiler.ir import PipelineIR
from dagwright.contracts import parse_contract_file

ROOT = Path(__file__).parents[1]
CUSTOMER = ROOT / "examples/contracts/customer-360.json"
GOLDEN = ROOT / "tests/golden/airflow"
CAPABILITIES = ROOT / "adapters/airflow/capabilities-v1alpha1.json"


def customer_ir() -> PipelineIR:
    return compile_contract(parse_contract_file(CUSTOMER)).ir


def test_published_capabilities_are_current_and_explicit() -> None:
    document = cast(dict[str, Any], json.loads(capability_bytes()))

    assert CAPABILITIES.read_bytes() == capability_bytes()
    assert document["target"] == "apache-airflow"
    assert document["targetVersion"] == ">=3.0,<4"
    assert document["generationOnly"] is True
    assert document["streaming"] is False
    assert document["cdc"] == "delegated_to_source"
    assert document["watermarks"] == "delegated_to_workload"
    assert document["exactlyOnceScope"] == "none"
    assert document["qualityGates"] == "structural_fail_closed"
    assert document["operationalContracts"] == "quality_fail_closed_others_delegated"


def test_customer_generation_matches_exact_golden_files() -> None:
    bundle = Airflow3Adapter().generate(customer_ir())

    assert bundle.artifact.content == (GOLDEN / "customer-360.py").read_bytes()
    assert bundle.manifest_bytes == (GOLDEN / "customer-360.manifest.json").read_bytes()


def test_generation_is_repeatable_and_does_not_import_airflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "airflow" or name.startswith("airflow."):
            raise AssertionError("adapter generation must not import Airflow")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    adapter = Airflow3Adapter()

    first = adapter.generate(customer_ir())
    second = adapter.generate(customer_ir())

    assert first == second
    assert not hasattr(adapter, "execute")
    assert not hasattr(adapter, "deploy")
    assert not hasattr(adapter, "apply")


def test_customer_dag_imports_with_real_airflow_3_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = Airflow3Adapter().generate(customer_ir())
    dag_file = tmp_path / "customer_360.py"
    dag_file.write_bytes(bundle.artifact.content)
    monkeypatch.setenv("AIRFLOW_HOME", str(tmp_path / "airflow-home"))

    spec = importlib.util.spec_from_file_location("generated_customer_360", dag_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dag = module.dag

    assert dag.dag_id == "dagwright__customer_360"
    assert dag.schedule == "*/5 * * * *"
    assert set(dag.task_dict) == {
        "source__customers_db",
        "asset__bronze_customers",
        "transformation__build_customer_profile",
        "asset__silver_customers",
        "quality__customer_id_required",
        "anomaly__customer_volume_change",
    }
    assert dag.task_dict["source__customers_db"].downstream_task_ids == {"asset__bronze_customers"}
    assert dag.task_dict["asset__bronze_customers"].downstream_task_ids == {
        "transformation__build_customer_profile"
    }
    assert dag.task_dict["transformation__build_customer_profile"].downstream_task_ids == {
        "asset__silver_customers"
    }
    assert dag.task_dict["asset__silver_customers"].downstream_task_ids == {
        "quality__customer_id_required",
        "anomaly__customer_volume_change",
    }
    assert all(task.retries == 0 for task in dag.task_dict.values())
    with pytest.raises(
        RuntimeError,
        match=r"Quality gate .* has no bound execution implementation",
    ):
        dag.task_dict["quality__customer_id_required"].python_callable()


def test_retry_attempts_map_to_airflow_retries() -> None:
    ir = customer_ir()
    first_node = ir.nodes[0].model_copy(update={"retry_policy": {"maxAttempts": 3}})
    changed = ir.model_copy(update={"nodes": (first_node, *ir.nodes[1:])})
    source = Airflow3Adapter().generate(changed).artifact.content.decode()

    assert '@task(task_id="anomaly__customer_volume_change", retries=2)' in source


def test_manual_schedule_renders_as_python_none() -> None:
    ir = customer_ir()
    execution = ir.execution.model_copy(update={"schedule": None})
    manual = ir.model_copy(update={"execution": execution})

    source = Airflow3Adapter().generate(manual).artifact.content.decode()

    assert "    schedule=None," in source
    compile(source, "generated_manual_dag.py", "exec")


def test_colliding_airflow_task_ids_are_rejected() -> None:
    ir = customer_ir()
    original = ir.nodes[1]
    collision = original.model_copy(
        update={
            "stable_id": "urn:dagwright:customer-360:asset:bronze-customers",
            "name": "bronze-customers",
            "inputs": (),
            "outputs": (),
        }
    )
    changed = ir.model_copy(update={"nodes": (*ir.nodes, collision)})

    violations = Airflow3Adapter().validate(changed)

    assert any(violation.code == "task_id_collision" for violation in violations)
    with pytest.raises(UnsupportedSemanticsError, match="task_id_collision"):
        Airflow3Adapter().generate(changed)


def test_manifest_preserves_artifact_metadata_quality_gate_and_lineage() -> None:
    ir = customer_ir()
    bundle = Airflow3Adapter().generate(ir)
    metadata = bundle.manifest.artifacts[0]
    quality = next(task for task in bundle.manifest.tasks if task.kind == "quality")

    assert bundle.manifest.input_ir_digest == canonical_digest(ir)
    assert metadata.path == bundle.artifact.path
    assert metadata.sha256 == bundle.artifact.sha256
    assert metadata.size == len(bundle.artifact.content)
    assert quality.quality_gate is True
    assert quality.severity == "error"
    assert bundle.manifest.delegated_operational_contracts == ir.operational_contracts
    assert len(bundle.manifest.lineage) == len(ir.edges)
    assert {
        (edge.upstream_stable_id, edge.downstream_stable_id) for edge in bundle.manifest.lineage
    } == {(edge.source, edge.target) for edge in ir.edges}


def test_unsupported_semantics_are_reported_together() -> None:
    ir = customer_ir()
    execution = ir.execution.model_copy(
        update={"orchestrator": "dagster", "schedule": "not a cron expression"}
    )
    source_index = next(index for index, node in enumerate(ir.nodes) if node.kind == "source")
    nodes = list(ir.nodes)
    semantics = deepcopy(nodes[source_index].execution_semantics)
    semantics["captureMode"] = "stream"
    nodes[source_index] = nodes[source_index].model_copy(
        update={
            "execution_semantics": semantics,
            "failure_policy": {"action": "continue"},
            "retry_policy": {"maxAttempts": 0},
        }
    )
    unsupported = ir.model_copy(update={"execution": execution, "nodes": tuple(nodes)})

    violations = Airflow3Adapter().validate(unsupported)
    codes = {violation.code for violation in violations}

    assert codes == {
        "streaming_not_supported",
        "unsupported_failure_policy",
        "unsupported_orchestrator",
        "unsupported_retry_policy",
        "unsupported_schedule",
    }
    with pytest.raises(UnsupportedSemanticsError) as caught:
        Airflow3Adapter().generate(unsupported)
    assert caught.value.violations == violations
