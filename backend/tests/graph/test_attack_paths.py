"""Phase 24 -- app/graph/queries.py::find_paths_to_critical_assets /
find_paths_between. Mirrors tests/graph/test_queries.py's style (real
Postgres, synthetic TECHNOLOGY nodes for pure traversal-shape tests, direct
sync-session GraphEdge inserts) and tests/graph/test_builder.py's style for
real Asset fixtures (HTTP API, since criticality lives on a real row these
queries actually filter by).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import async_session_factory
from app.db.sync_session import get_sync_session
from app.graph.queries import (
    MAX_ATTACK_PATH_HOPS,
    MAX_ATTACK_PATHS,
    InvalidDepthError,
    UnknownNodeTypeError,
    find_paths_between,
    find_paths_to_critical_assets,
)
from app.main import app
from app.models.asset import Asset
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
            reason="synthetic edge for attack-path tests",
        )
    )


async def _make_asset(criticality: str = "MEDIUM") -> str:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        project = (await ac.post("/api/projects", json={"name": "Attack Path Fixture"})).json()
        asset = (
            await ac.post(
                f"/api/projects/{project['id']}/assets",
                json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
            )
        ).json()
        if criticality != "MEDIUM":
            await ac.patch(f"/api/assets/{asset['id']}", json={"criticality": criticality})
    return asset["id"]


# --------------------------------------------------------------------------
# find_paths_between -- validates the traversal engine itself, deliberately
# usable with only the limited synthetic data these tests set up.
# --------------------------------------------------------------------------


async def test_between_finds_a_direct_path():
    prefix = uuid.uuid4().hex[:8]
    a, b = f"{prefix}-A", f"{prefix}-B"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", a, "TECHNOLOGY", b)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", b)

    assert len(result["paths"]) == 1
    path = result["paths"][0]
    assert path["hops"] == 1
    assert [n["id"] for n in path["nodes"]] == [a, b]
    assert "hypothes" in result["disclaimer"].lower()


async def test_between_finds_a_multi_hop_path():
    prefix = uuid.uuid4().hex[:8]
    a, b, c = f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", a, "TECHNOLOGY", b)
        _add_edge(session, "TECHNOLOGY", b, "TECHNOLOGY", c)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", c)

    assert len(result["paths"]) == 1
    assert result["paths"][0]["hops"] == 2
    assert [n["id"] for n in result["paths"][0]["nodes"]] == [a, b, c]
    assert [e["relation"] for e in result["paths"][0]["edges"]] == ["RELATED_TO", "RELATED_TO"]


async def test_between_no_path_returns_empty_list_not_an_error():
    prefix = uuid.uuid4().hex[:8]
    a, unreachable = f"{prefix}-A", f"{prefix}-UNREACHABLE"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", a, "TECHNOLOGY", f"{prefix}-B")
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", unreachable)

    assert result["paths"] == []
    assert result["truncated"] is False


async def test_between_source_equals_target_returns_empty_list_without_querying():
    prefix = uuid.uuid4().hex[:8]
    a = f"{prefix}-A"
    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", a)
    assert result["paths"] == []


async def test_between_respects_max_hops_bound():
    """A target only reachable at hop 3 must not appear when max_hops=2."""
    prefix = uuid.uuid4().hex[:8]
    a, b, c, d = f"{prefix}-A", f"{prefix}-B", f"{prefix}-C", f"{prefix}-D"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", a, "TECHNOLOGY", b)
        _add_edge(session, "TECHNOLOGY", b, "TECHNOLOGY", c)
        _add_edge(session, "TECHNOLOGY", c, "TECHNOLOGY", d)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        too_short = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", d, max_hops=2)
        assert too_short["paths"] == []

        long_enough = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", d, max_hops=3)
        assert len(long_enough["paths"]) == 1
        assert long_enough["paths"][0]["hops"] == 3


async def test_between_rejects_max_hops_above_ceiling():
    async with async_session_factory() as db:
        with pytest.raises(InvalidDepthError):
            await find_paths_between(db, "TECHNOLOGY", "x", "TECHNOLOGY", "y", max_hops=MAX_ATTACK_PATH_HOPS + 1)


async def test_between_rejects_unknown_node_type():
    async with async_session_factory() as db:
        with pytest.raises(UnknownNodeTypeError):
            await find_paths_between(db, "NOT_A_TYPE", "x", "TECHNOLOGY", "y")


async def test_between_handles_a_real_3_node_cycle_without_looping():
    prefix = uuid.uuid4().hex[:8]
    x, y, z, target = f"{prefix}-X", f"{prefix}-Y", f"{prefix}-Z", f"{prefix}-TARGET"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", x, "TECHNOLOGY", y)
        _add_edge(session, "TECHNOLOGY", y, "TECHNOLOGY", z)
        _add_edge(session, "TECHNOLOGY", z, "TECHNOLOGY", x)
        _add_edge(session, "TECHNOLOGY", z, "TECHNOLOGY", target)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        # Must terminate (not hang/loop forever) rather than follow the
        # X-Y-Z-X cycle indefinitely, and still find every real path to
        # `target` -- both the direct X-Z edge (traversal is bidirectional,
        # same convention as local_graph()) and the longer way around.
        result = await find_paths_between(db, "TECHNOLOGY", x, "TECHNOLOGY", target, max_hops=MAX_ATTACK_PATH_HOPS)

    node_paths = [[n["id"] for n in p["nodes"]] for p in result["paths"]]
    assert node_paths == [[x, z, target], [x, y, z, target]]  # shortest first


async def test_between_caps_at_max_attack_paths_and_reports_truncated():
    """MAX_ATTACK_PATHS + 5 distinct 2-hop routes from the same seed to the
    same target -- only MAX_ATTACK_PATHS are returned, and `truncated` says
    so honestly rather than silently dropping the rest.
    """
    prefix = uuid.uuid4().hex[:8]
    seed, target = f"{prefix}-SEED", f"{prefix}-TARGET"
    session = get_sync_session()
    try:
        for i in range(MAX_ATTACK_PATHS + 5):
            mid = f"{prefix}-MID-{i}"
            _add_edge(session, "TECHNOLOGY", seed, "TECHNOLOGY", mid)
            _add_edge(session, "TECHNOLOGY", mid, "TECHNOLOGY", target)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", seed, "TECHNOLOGY", target)

    assert len(result["paths"]) == MAX_ATTACK_PATHS
    assert result["truncated"] is True
    assert all(p["hops"] == 2 for p in result["paths"])


async def test_between_never_claims_exploitability_or_a_score():
    """No field anywhere in the response implies exploitability/probability
    -- only structural facts (hops, nodes, edges) and the disclaimer."""
    prefix = uuid.uuid4().hex[:8]
    a, b = f"{prefix}-A", f"{prefix}-B"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", a, "TECHNOLOGY", b)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_between(db, "TECHNOLOGY", a, "TECHNOLOGY", b)

    path = result["paths"][0]
    for forbidden in ("score", "probability", "likelihood", "exploitability", "confidence"):
        assert forbidden not in path
        assert forbidden not in result


# --------------------------------------------------------------------------
# find_paths_to_critical_assets
# --------------------------------------------------------------------------


async def test_critical_finds_path_to_a_critical_asset():
    critical_asset_id = await _make_asset(criticality="CRITICAL")
    prefix = uuid.uuid4().hex[:8]
    seed = f"{prefix}-ENTRY"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", seed, "ASSET", critical_asset_id, relation="RELATED_TO")
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_to_critical_assets(db, "TECHNOLOGY", seed)

    assert len(result["paths"]) == 1
    assert result["paths"][0]["nodes"][-1]["id"] == critical_asset_id
    assert result["paths"][0]["nodes"][-1]["type"] == "ASSET"


async def test_critical_ignores_non_critical_assets():
    medium_asset_id = await _make_asset(criticality="MEDIUM")
    prefix = uuid.uuid4().hex[:8]
    seed = f"{prefix}-ENTRY"
    session = get_sync_session()
    try:
        _add_edge(session, "TECHNOLOGY", seed, "ASSET", medium_asset_id, relation="RELATED_TO")
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_to_critical_assets(db, "TECHNOLOGY", seed)

    assert result["paths"] == []


async def test_critical_seed_already_critical_is_never_its_own_destination():
    critical_asset_id = await _make_asset(criticality="CRITICAL")
    prefix = uuid.uuid4().hex[:8]
    other = f"{prefix}-OTHER"
    session = get_sync_session()
    try:
        # A self-referencing-ish edge to something else, so the seed has at
        # least one edge -- the point is that the seed's OWN criticality
        # must never make it appear as a "path to itself" of length 0.
        _add_edge(session, "ASSET", critical_asset_id, "TECHNOLOGY", other)
        session.commit()
    finally:
        session.close()

    async with async_session_factory() as db:
        result = await find_paths_to_critical_assets(db, "ASSET", critical_asset_id)

    assert result["paths"] == []


async def test_critical_rejects_max_hops_above_ceiling():
    async with async_session_factory() as db:
        with pytest.raises(InvalidDepthError):
            await find_paths_to_critical_assets(db, "TECHNOLOGY", "x", max_hops=MAX_ATTACK_PATH_HOPS + 1)


async def test_critical_rejects_unknown_node_type():
    async with async_session_factory() as db:
        with pytest.raises(UnknownNodeTypeError):
            await find_paths_to_critical_assets(db, "NOT_A_TYPE", "x")
