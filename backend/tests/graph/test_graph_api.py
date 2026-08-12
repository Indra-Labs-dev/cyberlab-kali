import uuid
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.sync_session import get_sync_session
from app.graph.builder import build_graph_for_asset
from app.main import app
from app.models.asset import Asset


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_asset(client, technologies: list[str] | None = None, project_id: str | None = None) -> tuple[str, str]:
    if project_id is None:
        project = (await client.post("/api/projects", json={"name": "Graph API Fixture"})).json()
        project_id = project["id"]
    asset = (
        await client.post(
            f"/api/projects/{project_id}/assets",
            json={"name": "a", "hostname": "cyberlab-kali", "type": "CONTAINER"},
        )
    ).json()
    if technologies:
        session = get_sync_session()
        try:
            db_asset = session.get(Asset, uuid.UUID(asset["id"]))
            db_asset.technologies = technologies
            session.commit()
        finally:
            session.close()
    return project_id, asset["id"]


def _build(asset_id: str) -> None:
    session = get_sync_session()
    try:
        asset = session.get(Asset, uuid.UUID(asset_id))
        build_graph_for_asset(session, asset)
        session.commit()
    finally:
        session.close()


async def test_get_asset_graph_404_for_unknown_asset(client):
    response = await client.get(f"/api/graph/assets/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_asset_graph_returns_seed_node_even_with_no_edges(client):
    _, asset_id = await _make_asset(client)
    response = await client.get(f"/api/graph/assets/{asset_id}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["type"] == "ASSET"
    assert body["edges"] == []


async def test_get_asset_graph_includes_technology_edges(client):
    _, asset_id = await _make_asset(client, technologies=["Apache"])
    _build(asset_id)

    response = await client.get(f"/api/graph/assets/{asset_id}")
    assert response.status_code == 200
    body = response.json()
    tech_edges = [e for e in body["edges"] if e["relation"] == "USES_TECHNOLOGY"]
    assert len(tech_edges) == 1
    assert tech_edges[0]["to_id"] == "Apache"


async def test_get_asset_graph_rejects_depth_zero(client):
    _, asset_id = await _make_asset(client)
    response = await client.get(f"/api/graph/assets/{asset_id}", params={"depth": 0})
    assert response.status_code == 422


async def test_get_asset_graph_rejects_negative_depth(client):
    _, asset_id = await _make_asset(client)
    response = await client.get(f"/api/graph/assets/{asset_id}", params={"depth": -1})
    assert response.status_code == 422


async def test_get_asset_graph_rejects_depth_above_max(client):
    _, asset_id = await _make_asset(client)
    response = await client.get(f"/api/graph/assets/{asset_id}", params={"depth": 4})
    assert response.status_code == 422


async def test_get_finding_graph_404_for_unknown_finding(client):
    response = await client.get(f"/api/graph/findings/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_node_graph_400_for_unknown_type(client):
    response = await client.get(f"/api/graph/nodes/NOT_A_TYPE/{uuid.uuid4()}")
    assert response.status_code == 400


async def test_get_node_graph_404_for_unknown_asset(client):
    response = await client.get(f"/api/graph/nodes/ASSET/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_node_graph_virtual_type_never_404s(client):
    # CVE/SERVICE/TECHNOLOGY have no backing table -- an unknown one is an
    # empty graph (honest answer), never a 404.
    response = await client.get(f"/api/graph/nodes/CVE/CVE-9999-{uuid.uuid4().hex[:8]}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 1
    assert body["edges"] == []


async def test_get_node_graph_rejects_sql_injection_attempt_in_node_id(client):
    # Parameterized query -- a malicious node_id is treated as an inert
    # string, never interpolated into SQL. Must not 500, must not affect
    # other data.
    response = await client.get("/api/graph/nodes/TECHNOLOGY/'; DROP TABLE graph_edges; --")
    assert response.status_code == 200
    body = response.json()
    assert body["edges"] == []

    # Table still intact and queryable afterward.
    check = await client.get(f"/api/graph/assets/{uuid.uuid4()}")
    assert check.status_code == 404  # would 500 if the table were gone


async def test_get_project_graph_404_for_unknown_project(client):
    response = await client.get(f"/api/graph/projects/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_project_graph_never_leaks_assets_from_other_projects(client):
    project_a, asset_a = await _make_asset(client)
    project_b, asset_b = await _make_asset(client)
    _build(asset_a)
    _build(asset_b)

    response = await client.get(f"/api/graph/projects/{project_a}")
    assert response.status_code == 200
    node_ids = {n["id"] for n in response.json()["nodes"]}
    assert asset_a in node_ids
    assert asset_b not in node_ids


async def test_rebuild_enqueues_and_returns_202(client, monkeypatch):
    mock_queue = MagicMock()
    monkeypatch.setattr("app.api.routes.graph.get_queue", lambda: mock_queue)

    response = await client.post("/api/graph/rebuild", json={})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    mock_queue.enqueue.assert_called_once()


async def test_rebuild_accepts_no_body(client, monkeypatch):
    mock_queue = MagicMock()
    monkeypatch.setattr("app.api.routes.graph.get_queue", lambda: mock_queue)

    response = await client.post("/api/graph/rebuild")
    assert response.status_code == 202
