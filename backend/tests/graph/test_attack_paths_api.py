"""Phase 24 -- GET /api/graph/attack-paths/critical/{type}/{id} and
GET /api/graph/attack-paths/between/{...}. Mirrors tests/graph/
test_graph_api.py's style (real HTTP via httpx, real Postgres).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.graph.builder import build_graph_for_asset
from app.graph.queries import MAX_ATTACK_PATH_HOPS
from app.main import app
from app.models.asset import Asset


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_asset(client, criticality: str = "MEDIUM") -> str:
    project = (await client.post("/api/projects", json={"name": "Attack Path API Fixture"})).json()
    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    if criticality != "MEDIUM":
        await client.patch(f"/api/assets/{asset['id']}", json={"criticality": criticality})
    return asset["id"]


def _build(asset_id: str) -> None:
    session = get_sync_session()
    try:
        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()
    finally:
        session.close()


# --------------------------------------------------------------------------
# /attack-paths/critical/{node_type}/{node_id}
# --------------------------------------------------------------------------


async def test_critical_404_for_unknown_asset(client):
    response = await client.get(f"/api/graph/attack-paths/critical/ASSET/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_critical_400_for_unknown_node_type(client):
    response = await client.get(f"/api/graph/attack-paths/critical/NOT_A_TYPE/{uuid.uuid4()}")
    assert response.status_code == 400


async def test_critical_virtual_type_never_404s(client):
    response = await client.get(f"/api/graph/attack-paths/critical/TECHNOLOGY/nonexistent-{uuid.uuid4().hex[:8]}")
    assert response.status_code == 200
    assert response.json()["paths"] == []


async def test_critical_rejects_max_hops_above_ceiling(client):
    response = await client.get(
        f"/api/graph/attack-paths/critical/TECHNOLOGY/x?max_hops={MAX_ATTACK_PATH_HOPS + 1}"
    )
    assert response.status_code == 422


async def test_critical_response_always_carries_the_disclaimer(client):
    response = await client.get(f"/api/graph/attack-paths/critical/TECHNOLOGY/nonexistent-{uuid.uuid4().hex[:8]}")
    body = response.json()
    assert "disclaimer" in body
    assert "hypothes" in body["disclaimer"].lower()
    assert "truncated" in body


async def test_critical_end_to_end_via_real_builder_derived_edges(client):
    """Two assets sharing a technology in the same project produce a real
    RELATED_TO edge (app/graph/builder.py) -- if one is CRITICAL, a path
    from the other must be found through data the builder actually derived,
    not synthetic test-only edges.
    """
    project = (await client.post("/api/projects", json={"name": "Attack Path E2E"})).json()
    entry = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "entry", "hostname": "entry.local", "type": "CONTAINER"},
        )
    ).json()
    critical = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "critical", "hostname": "critical.local", "type": "CONTAINER"},
        )
    ).json()
    await client.patch(f"/api/assets/{critical['id']}", json={"criticality": "CRITICAL"})

    session = get_sync_session()
    try:
        for aid in (entry["id"], critical["id"]):
            db_asset = session.get(Asset, uuid.UUID(aid))
            db_asset.technologies = ["nginx"]
        session.commit()
    finally:
        session.close()
    _build(entry["id"])
    _build(critical["id"])

    response = await client.get(f"/api/graph/attack-paths/critical/ASSET/{entry['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["paths"]) >= 1
    assert any(p["nodes"][-1]["id"] == critical["id"] for p in body["paths"])


# --------------------------------------------------------------------------
# /attack-paths/between/{from_type}/{from_id}/{to_type}/{to_id}
# --------------------------------------------------------------------------


async def test_between_404_for_unknown_source_asset(client):
    response = await client.get(f"/api/graph/attack-paths/between/ASSET/{uuid.uuid4()}/TECHNOLOGY/x")
    assert response.status_code == 404


async def test_between_404_for_unknown_target_finding(client):
    asset_id = await _make_asset(client)
    response = await client.get(f"/api/graph/attack-paths/between/ASSET/{asset_id}/FINDING/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_between_400_for_unknown_node_type(client):
    response = await client.get(f"/api/graph/attack-paths/between/NOT_A_TYPE/x/TECHNOLOGY/y")
    assert response.status_code == 400


async def test_between_source_equals_target_returns_empty_paths(client):
    response = await client.get("/api/graph/attack-paths/between/TECHNOLOGY/same/TECHNOLOGY/same")
    assert response.status_code == 200
    assert response.json()["paths"] == []


async def test_between_rejects_sql_injection_attempt_in_node_id(client):
    response = await client.get(
        "/api/graph/attack-paths/between/TECHNOLOGY/'; DROP TABLE graph_edges; --/TECHNOLOGY/y"
    )
    assert response.status_code == 200
    assert response.json()["paths"] == []

    # Table still intact and queryable afterward.
    check = await client.get(f"/api/graph/assets/{uuid.uuid4()}")
    assert check.status_code == 404  # would 500 if the table were gone


async def test_between_end_to_end_via_real_builder_derived_edges(client):
    project = (await client.post("/api/projects", json={"name": "Attack Path Between E2E"})).json()
    a = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "a", "hostname": "a.local", "type": "CONTAINER"},
        )
    ).json()
    b = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "b", "hostname": "b.local", "type": "CONTAINER"},
        )
    ).json()

    session = get_sync_session()
    try:
        for aid in (a["id"], b["id"]):
            db_asset = session.get(Asset, uuid.UUID(aid))
            db_asset.technologies = ["apache"]
        session.commit()
    finally:
        session.close()
    _build(a["id"])
    _build(b["id"])

    response = await client.get(f"/api/graph/attack-paths/between/ASSET/{a['id']}/ASSET/{b['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["paths"]) >= 1
    assert body["paths"][0]["nodes"][0]["id"] == a["id"]
    assert body["paths"][0]["nodes"][-1]["id"] == b["id"]
