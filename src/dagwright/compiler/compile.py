"""Compile a validated DataProduct into the canonical engine-neutral IR."""

import hashlib
from dataclasses import dataclass

import networkx as nx
from pydantic import JsonValue

from dagwright.compiler.canonical import canonical_bytes, canonical_digest, normalize_contract
from dagwright.compiler.errors import (
    CycleError,
    MissingReferenceError,
    ReferenceResolutionError,
    SchemaCompatibilityError,
)
from dagwright.compiler.ir import (
    DependencyEdge,
    IRExecution,
    IRGovernance,
    PipelineIR,
    PipelineNode,
    SchemaCompatibilityHook,
    node_index,
)
from dagwright.contracts.models import ContractModel, DataProduct


@dataclass(frozen=True)
class CompilationResult:
    """Canonical contract and IR artifacts with their content digests."""

    contract: DataProduct
    contract_bytes: bytes
    contract_digest: str
    ir: PipelineIR
    ir_bytes: bytes
    ir_digest: str


def compile_contract(
    contract: DataProduct,
    *,
    schema_hooks: tuple[SchemaCompatibilityHook, ...] = (),
) -> CompilationResult:
    """Normalize, resolve, validate, and compile a DataProduct deterministically."""
    normalized = normalize_contract(contract)
    _validate_references(normalized)
    contract_digest = canonical_digest(normalized)
    nodes, edges = _build_graph(normalized)
    _detect_cycle(nodes, edges)
    _run_schema_hooks(nodes, edges, schema_hooks)
    ir = PipelineIR(
        ir_version="dagwright.ir/v1alpha1",
        data_product_id=_stable_id(normalized.metadata.name, "dataproduct"),
        contract_api_version=normalized.api_version,
        contract_version=normalized.version,
        contract_digest=contract_digest,
        nodes=nodes,
        edges=edges,
        operational_contracts=normalized.contracts.model_dump(mode="json", by_alias=True),
        execution=IRExecution(
            transform_engine=normalized.execution.transform_engine,
            orchestrator=normalized.execution.orchestrator,
            target_catalog=normalized.execution.target_catalog,
            schedule=normalized.execution.schedule,
            resources=_json_dict(normalized.execution.resources),
        ),
        governance=IRGovernance(
            data_classification=normalized.governance.data_classification,
            production_repair_policy=normalized.governance.production_repair_policy,
            pii_fields=tuple(normalized.governance.pii_fields),
            retention=normalized.governance.retention,
        ),
    )
    ir_bytes = canonical_bytes(ir)
    return CompilationResult(
        contract=normalized,
        contract_bytes=canonical_bytes(normalized),
        contract_digest=contract_digest,
        ir=ir,
        ir_bytes=ir_bytes,
        ir_digest=hashlib.sha256(ir_bytes).hexdigest(),
    )


def _validate_references(contract: DataProduct) -> None:
    sources = {source.name for source in contract.sources}
    assets = {asset.name for asset in contract.assets}
    assets_by_name = {asset.name: asset for asset in contract.assets}
    transformations = {item.id: item for item in contract.transformations}
    missing: list[str] = []
    for asset in contract.assets:
        if asset.source is not None:
            source_name = asset.source.split(".", maxsplit=1)[0]
            if source_name not in sources:
                missing.append(f"assets.{asset.name}.source -> source {source_name!r}")
        for input_name in asset.inputs:
            if input_name not in assets:
                missing.append(f"assets.{asset.name}.inputs -> asset {input_name!r}")
        for transformation_id in asset.transformation_ids:
            transformation = transformations.get(transformation_id)
            if transformation is None:
                missing.append(
                    f"assets.{asset.name}.transformationIds -> transformation {transformation_id!r}"
                )
            elif transformation.output != asset.name:
                missing.append(
                    f"assets.{asset.name}.transformationIds -> "
                    f"transformation {transformation_id!r} "
                    f"outputs {transformation.output!r}"
                )
    for transformation in contract.transformations:
        for input_name in transformation.inputs:
            if input_name not in assets:
                missing.append(
                    f"transformations.{transformation.id}.inputs -> asset {input_name!r}"
                )
        if transformation.output not in assets:
            missing.append(
                f"transformations.{transformation.id}.output -> asset {transformation.output!r}"
            )
        else:
            output_asset = assets_by_name[transformation.output]
            if transformation.id not in output_asset.transformation_ids:
                missing.append(
                    f"transformations.{transformation.id} -> not referenced by output asset "
                    f"{transformation.output!r}"
                )
            elif set(transformation.inputs) != set(output_asset.inputs):
                raise ReferenceResolutionError(
                    f"transformation {transformation.id!r} inputs do not match output asset "
                    f"{transformation.output!r} inputs"
                )
    for quality_rule in contract.contracts.quality:
        if quality_rule.asset not in assets:
            missing.append(
                f"contracts.quality.{quality_rule.id}.asset -> asset {quality_rule.asset!r}"
            )
        if quality_rule.reference is not None:
            reference_parts = quality_rule.reference.split(".", maxsplit=1)
            if len(reference_parts) != 2 or not reference_parts[1]:
                raise ReferenceResolutionError(
                    f"quality reference {quality_rule.reference!r} must use 'asset.field' syntax"
                )
            reference_asset = reference_parts[0]
            if reference_asset not in assets:
                missing.append(
                    f"contracts.quality.{quality_rule.id}.reference -> asset {reference_asset!r}"
                )
    for anomaly_rule in contract.contracts.anomalies:
        if anomaly_rule.asset not in assets:
            missing.append(
                f"contracts.anomalies.{anomaly_rule.id}.asset -> asset {anomaly_rule.asset!r}"
            )
    if missing:
        raise MissingReferenceError(
            "unresolved contract reference(s): " + "; ".join(sorted(missing))
        )


def _build_graph(
    contract: DataProduct,
) -> tuple[tuple[PipelineNode, ...], tuple[DependencyEdge, ...]]:
    product = contract.metadata.name
    source_ids = {
        source.name: _stable_id(product, "source", source.name) for source in contract.sources
    }
    asset_ids = {asset.name: _stable_id(product, "asset", asset.name) for asset in contract.assets}
    transform_ids = {
        item.id: _stable_id(product, "transformation", item.id) for item in contract.transformations
    }
    edge_specs: set[tuple[str, str, str]] = set()

    for asset in contract.assets:
        asset_id = asset_ids[asset.name]
        if asset.source is not None:
            source_name = asset.source.split(".", maxsplit=1)[0]
            edge_specs.add((source_ids[source_name], asset_id, "reads"))
        linked = [
            contract_transform
            for contract_transform in contract.transformations
            if contract_transform.output == asset.name
            and contract_transform.id in asset.transformation_ids
        ]
        if linked:
            for transformation in linked:
                transform_id = transform_ids[transformation.id]
                for input_name in transformation.inputs:
                    edge_specs.add((asset_ids[input_name], transform_id, "transforms"))
                edge_specs.add((transform_id, asset_id, "transforms"))
        else:
            for input_name in asset.inputs:
                edge_specs.add((asset_ids[input_name], asset_id, "depends_on"))

    quality_ids = {
        rule.id: _stable_id(product, "quality", rule.id) for rule in contract.contracts.quality
    }
    anomaly_ids = {
        rule.id: _stable_id(product, "anomaly", rule.id) for rule in contract.contracts.anomalies
    }
    for quality_rule in contract.contracts.quality:
        edge_specs.add((asset_ids[quality_rule.asset], quality_ids[quality_rule.id], "validates"))
    for anomaly_rule in contract.contracts.anomalies:
        edge_specs.add((asset_ids[anomaly_rule.asset], anomaly_ids[anomaly_rule.id], "observes"))

    edges = tuple(
        DependencyEdge(
            stable_id=_edge_id(product, source, target, kind),
            source=source,
            target=target,
            kind=kind,  # type: ignore[arg-type]
        )
        for source, target, kind in sorted(edge_specs)
    )
    inputs: dict[str, list[str]] = {}
    outputs: dict[str, list[str]] = {}
    for edge in edges:
        inputs.setdefault(edge.target, []).append(edge.source)
        outputs.setdefault(edge.source, []).append(edge.target)

    nodes: list[PipelineNode] = []
    for index, source in enumerate(contract.sources):
        stable_id = source_ids[source.name]
        nodes.append(
            _node(
                stable_id,
                "source",
                source.name,
                inputs,
                outputs,
                f"/sources/{index}",
                {
                    "type": source.type,
                    "object": source.object,
                    "captureMode": source.capture.mode,
                    "deleteSemantics": source.capture.delete_semantics,
                    "cursorField": source.capture.cursor_field,
                },
                source,
                security_context={"connectionRef": source.connection_ref},
            )
        )
    for index, asset in enumerate(contract.assets):
        stable_id = asset_ids[asset.name]
        nodes.append(
            _node(
                stable_id,
                "asset",
                asset.name,
                inputs,
                outputs,
                f"/assets/{index}",
                {
                    "type": asset.type,
                    "mode": asset.mode,
                    "primaryKey": list(asset.primary_key),
                    "retention": asset.retention,
                    "transformationIds": list(asset.transformation_ids),
                },
                asset,
            )
        )
    for index, transformation in enumerate(contract.transformations):
        stable_id = transform_ids[transformation.id]
        nodes.append(
            _node(
                stable_id,
                "transformation",
                transformation.id,
                inputs,
                outputs,
                f"/transformations/{index}",
                {
                    "type": transformation.type,
                    "implementationRef": transformation.sql_ref or transformation.python_ref,
                },
                transformation,
                resource_hints=_json_dict(contract.execution.resources),
            )
        )
    for index, quality_rule in enumerate(contract.contracts.quality):
        stable_id = quality_ids[quality_rule.id]
        nodes.append(
            _node(
                stable_id,
                "quality",
                quality_rule.id,
                inputs,
                outputs,
                f"/contracts/quality/{index}",
                {
                    "type": quality_rule.type,
                    "fields": list(quality_rule.fields),
                    "reference": quality_rule.reference,
                    "severity": quality_rule.severity,
                },
                quality_rule,
            )
        )
    for index, anomaly_rule in enumerate(contract.contracts.anomalies):
        stable_id = anomaly_ids[anomaly_rule.id]
        nodes.append(
            _node(
                stable_id,
                "anomaly",
                anomaly_rule.id,
                inputs,
                outputs,
                f"/contracts/anomalies/{index}",
                {
                    "metric": anomaly_rule.metric,
                    "method": anomaly_rule.method,
                    "threshold": anomaly_rule.threshold,
                    "window": anomaly_rule.window,
                    "severity": anomaly_rule.severity,
                },
                anomaly_rule,
            )
        )
    retry_policy: dict[str, JsonValue] = {
        "maxAttempts": contract.execution.retry.max_attempts,
    }
    idempotency = contract.execution.idempotency.model_dump(mode="json", by_alias=True)
    governed_nodes = tuple(
        node.model_copy(
            update={
                "execution_semantics": {
                    **node.execution_semantics,
                    "idempotency": idempotency,
                },
                "retry_policy": retry_policy,
            }
        )
        for node in nodes
    )
    return tuple(sorted(governed_nodes, key=lambda node: node.stable_id)), edges


def _node(
    stable_id: str,
    kind: str,
    name: str,
    inputs: dict[str, list[str]],
    outputs: dict[str, list[str]],
    location: str,
    semantics: dict[str, JsonValue],
    contract_object: ContractModel,
    *,
    resource_hints: dict[str, JsonValue] | None = None,
    security_context: dict[str, JsonValue] | None = None,
) -> PipelineNode:
    return PipelineNode(
        stable_id=stable_id,
        kind=kind,  # type: ignore[arg-type]
        name=name,
        inputs=tuple(sorted(inputs.get(stable_id, []))),
        outputs=tuple(sorted(outputs.get(stable_id, []))),
        execution_semantics=semantics,
        resource_hints=resource_hints,
        security_context=security_context or {},
        lineage_metadata={"provenance": "declared"},
        source_contract_location=location,
        extension_fields=dict(contract_object.model_extra or {}),
    )


def _detect_cycle(nodes: tuple[PipelineNode, ...], edges: tuple[DependencyEdge, ...]) -> None:
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node.stable_id for node in nodes)
    graph.add_edges_from((edge.source, edge.target) for edge in edges)
    if nx.is_directed_acyclic_graph(graph):
        return
    cycle = nx.find_cycle(graph)
    path = " -> ".join([source for source, _ in cycle] + [cycle[0][0]])
    raise CycleError(f"dependency cycle detected: {path}")


def _run_schema_hooks(
    nodes: tuple[PipelineNode, ...],
    edges: tuple[DependencyEdge, ...],
    hooks: tuple[SchemaCompatibilityHook, ...],
) -> None:
    index = node_index(nodes)
    failures: list[str] = []
    for edge in edges:
        if edge.kind not in {"reads", "depends_on", "transforms"}:
            continue
        for hook in hooks:
            failures.extend(
                f"{hook.name} rejected {edge.source} -> {edge.target}: {message}"
                for message in hook.check(index[edge.source], index[edge.target])
            )
    if failures:
        raise SchemaCompatibilityError("schema compatibility failure(s): " + "; ".join(failures))


def _stable_id(product: str, kind: str, name: str | None = None) -> str:
    suffix = f":{name}" if name is not None else ""
    return f"urn:dagwright:{product}:{kind}{suffix}"


def _edge_id(product: str, source: str, target: str, kind: str) -> str:
    digest = hashlib.sha256(f"{source}\0{target}\0{kind}".encode()).hexdigest()[:24]
    return _stable_id(product, "edge", f"e_{digest}")


def _json_dict(model: ContractModel | None) -> dict[str, JsonValue] | None:
    if model is None:
        return None
    return model.model_dump(mode="json", by_alias=True)
