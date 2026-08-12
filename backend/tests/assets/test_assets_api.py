import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_project_and_asset(client, **asset_overrides):
    project = (await client.post("/api/projects", json={"name": "Fixture Project"})).json()
    payload = {"name": "Fixture Asset", "hostname": "10.0.0.9", "type": "IP"}
    payload.update(asset_overrides)
    asset = (await client.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
    return project, asset


async def test_create_asset_defaults_criticality_medium_and_empty_derived_fields(client):
    _, asset = await _make_project_and_asset(client)
    assert asset["criticality"] == "MEDIUM"
    assert asset["tags"] == []
    assert asset["technologies"] == []
    assert asset["first_seen"] is None
    assert asset["last_seen"] is None


async def test_create_asset_accepts_criticality_and_tags(client):
    _, asset = await _make_project_and_asset(
        client, criticality="CRITICAL", tags=["prod", "external"]
    )
    assert asset["criticality"] == "CRITICAL"
    assert set(asset["tags"]) == {"prod", "external"}


async def test_create_asset_new_types_accepted(client):
    for asset_type in ("SUBDOMAIN", "SERVICE", "LAB_RESOURCE"):
        _, asset = await _make_project_and_asset(client, type=asset_type, name=asset_type)
        assert asset["type"] == asset_type


async def test_get_asset(client):
    _, asset = await _make_project_and_asset(client)
    response = await client.get(f"/api/assets/{asset['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == asset["id"]


async def test_get_nonexistent_asset_404(client):
    response = await client.get("/api/assets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_update_asset_criticality(client):
    _, asset = await _make_project_and_asset(client)
    response = await client.patch(f"/api/assets/{asset['id']}", json={"criticality": "HIGH"})
    assert response.status_code == 200
    assert response.json()["criticality"] == "HIGH"


async def test_update_asset_cannot_remove_all_addresses(client):
    _, asset = await _make_project_and_asset(client)
    response = await client.patch(f"/api/assets/{asset['id']}", json={"hostname": None})
    assert response.status_code == 422


async def test_update_asset_cannot_set_first_seen_directly(client):
    """first_seen/last_seen/technologies are derived from real Job activity
    (app/assets/activity.py) -- the update schema has no field for them, so
    an attempt to set them is silently ignored by pydantic, not persisted."""
    _, asset = await _make_project_and_asset(client)
    response = await client.patch(
        f"/api/assets/{asset['id']}", json={"first_seen": "2020-01-01T00:00:00Z"}
    )
    assert response.status_code == 200
    assert response.json()["first_seen"] is None


async def test_delete_asset(client):
    _, asset = await _make_project_and_asset(client)
    response = await client.delete(f"/api/assets/{asset['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/api/assets/{asset['id']}")).status_code == 404


async def test_list_assets_filters_by_project(client):
    project_a, asset_a = await _make_project_and_asset(client, name="A")
    project_b = (await client.post("/api/projects", json={"name": "Project B"})).json()
    await client.post(
        f"/api/projects/{project_b['id']}/assets",
        json={"name": "B", "hostname": "10.0.0.10", "type": "IP"},
    )

    response = await client.get(f"/api/assets?project_id={project_a['id']}")
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert asset_a["id"] in ids
    assert all(a["project_id"] == project_a["id"] for a in response.json())


async def test_list_assets_filters_by_criticality(client):
    await _make_project_and_asset(client, name="crit-one", criticality="CRITICAL")
    response = await client.get("/api/assets?criticality=CRITICAL")
    assert response.status_code == 200
    assert response.json()
    assert all(a["criticality"] == "CRITICAL" for a in response.json())


async def test_target_and_asset_apis_see_the_same_row(client):
    """Target (Phase 11) is now a special case of Asset (Phase 13) -- same
    table, same primary key. Creating via the legacy /targets-nested route
    must be visible via /api/assets and vice versa."""
    project = (await client.post("/api/projects", json={"name": "Compat Project"})).json()
    target = (
        await client.post(
            f"/api/projects/{project['id']}/targets",
            json={"name": "Legacy Target", "hostname": "10.0.0.11", "target_type": "IP"},
        )
    ).json()

    via_assets = await client.get(f"/api/assets/{target['id']}")
    assert via_assets.status_code == 200
    body = via_assets.json()
    assert body["type"] == "IP"
    assert body["criticality"] == "MEDIUM"  # Phase 13 default, absent from the legacy request

    asset = (
        await client.post(
            f"/api/projects/{project['id']}/assets",
            json={"name": "New Asset", "hostname": "10.0.0.12", "type": "SUBDOMAIN"},
        )
    ).json()
    via_targets = await client.get(f"/api/targets/{asset['id']}")
    assert via_targets.status_code == 200
    assert via_targets.json()["target_type"] == "SUBDOMAIN"
