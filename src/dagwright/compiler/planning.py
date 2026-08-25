"""Deterministic execution planning over canonical DAGwright IR."""

from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from dagwright.compiler.errors import CycleError
from dagwright.compiler.ir import PipelineIR


class PlanModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class PlanStep(PlanModel):
    position: int
    stable_id: str
    kind: str
    name: str
    dependencies: tuple[str, ...]


class ExecutionPlan(PlanModel):
    api_version: Literal["dagwright.io/execution-plan/v1alpha1"]
    data_product_id: str
    steps: tuple[PlanStep, ...]


def build_execution_plan(ir: PipelineIR) -> ExecutionPlan:
    """Return a stable topological plan, rejecting cyclic or incomplete graphs."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    nodes = {node.stable_id: node for node in ir.nodes}
    graph.add_nodes_from(sorted(nodes))
    for edge in ir.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise CycleError(f"graph edge references an unknown node: {edge.stable_id}")
        graph.add_edge(edge.source, edge.target)
    try:
        ordered = tuple(nx.lexicographical_topological_sort(graph, key=str))
    except nx.NetworkXUnfeasible as error:
        cycle = nx.find_cycle(graph)
        path = " -> ".join([source for source, _ in cycle] + [cycle[0][0]])
        raise CycleError(f"dependency cycle detected: {path}") from error
    return ExecutionPlan(
        api_version="dagwright.io/execution-plan/v1alpha1",
        data_product_id=ir.data_product_id,
        steps=tuple(
            PlanStep(
                position=index,
                stable_id=stable_id,
                kind=nodes[stable_id].kind,
                name=nodes[stable_id].name,
                dependencies=tuple(sorted(graph.predecessors(stable_id))),
            )
            for index, stable_id in enumerate(ordered, start=1)
        ),
    )
