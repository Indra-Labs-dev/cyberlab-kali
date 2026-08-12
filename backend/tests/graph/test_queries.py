import uuid

import pytest

from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.graph.queries import MAX_GRAPH_DEPTH, InvalidDepthError, UnknownNodeTypeError, local_graph
from app.models.graph_edge import GraphEdge


def _add_edge(session, from_type, from_id, to_type, to_id, relation="RELATED_TO", source="test") -> None:
    session.add(
        GraphEdge(
            id=uuid.uuid4(),
            from_type=from_type,
            from_id=from_id,
            to_type=to_type,
            to_id=to_id,
            relation=relation,
            source=source,
            reason="synthetic edge for query tests",
        )
    )


async def test_local_graph_depth_1_returns_direct_edges_only():
    prefix = uuid.uuid4().hex[:8]
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", f"{prefix}-A", "TECHNOLOGY", f"{prefix}-B")
        _add_edge(session, "TECHNOLOGY", f"{prefix}-B", "TECHNOLOGY", f"{prefix}-C")
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        graph = await local_graph(db, "TECHNOLOGY", f"{prefix}-A", 1)
        node_ids = {n["id"] for n in graph["nodes"]}
        assert node_ids == {f"{prefix}-A", f"{prefix}-B"}
        assert len(graph["edges"]) == 1


async def test_local_graph_depth_2_reaches_second_hop():
    prefix = uuid.uuid4().hex[:8]
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", f"{prefix}-A", "TECHNOLOGY", f"{prefix}-B")
        _add_edge(session, "TECHNOLOGY", f"{prefix}-B", "TECHNOLOGY", f"{prefix}-C")
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        graph = await local_graph(db, "TECHNOLOGY", f"{prefix}-A", 2)
        node_ids = {n["id"] for n in graph["nodes"]}
        assert node_ids == {f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"}
        assert len(graph["edges"]) == 2


async def test_local_graph_seed_node_with_zero_edges_still_returned():
    lone = uuid.uuid4().hex
    async with async_session_factory() as db:
        graph = await local_graph(db, "TECHNOLOGY", lone, 1)
        assert graph["nodes"] == [{"id": lone, "type": "TECHNOLOGY", "label": lone, "metadata": {}}]
        assert graph["edges"] == []


async def test_local_graph_handles_a_real_3_node_cycle_without_looping():
    prefix = uuid.uuid4().hex[:8]
    x, y, z = f"{prefix}-X", f"{prefix}-Y", f"{prefix}-Z"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", x, "TECHNOLOGY", y)
        _add_edge(session, "TECHNOLOGY", y, "TECHNOLOGY", z)
        _add_edge(session, "TECHNOLOGY", z, "TECHNOLOGY", x)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        graph = await local_graph(db, "TECHNOLOGY", x, MAX_GRAPH_DEPTH)
        assert {n["id"] for n in graph["nodes"]} == {x, y, z}
        assert len(graph["edges"]) == 3  # all 3 cycle edges found, traversal terminated


async def test_local_graph_rejects_depth_above_max():
    async with async_session_factory() as db:
        with pytest.raises(InvalidDepthError):
            await local_graph(db, "TECHNOLOGY", "x", MAX_GRAPH_DEPTH + 1)


async def test_local_graph_rejects_depth_below_one():
    async with async_session_factory() as db:
        with pytest.raises(InvalidDepthError):
            await local_graph(db, "TECHNOLOGY", "x", 0)


async def test_local_graph_rejects_unknown_node_type():
    async with async_session_factory() as db:
        with pytest.raises(UnknownNodeTypeError):
            await local_graph(db, "NOT_A_TYPE", "x", 1)
