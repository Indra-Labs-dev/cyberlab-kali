from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.assets.activity import record_asset_activity, technologies_from_whatweb
from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.main import app
from app.models.asset import Asset


def test_technologies_from_whatweb_extracts_plugin_names():
    parsed = {
        "results": [
            {"target": "http://x", "plugins": {"nginx": {}, "PHP": {}}},
            {"target": "http://y", "plugins": {"nginx": {}}},
        ]
    }
    assert technologies_from_whatweb(parsed) == ["PHP", "nginx"]


def test_technologies_from_whatweb_empty_when_no_plugins():
    assert technologies_from_whatweb({"results": []}) == []


async def _make_project_and_target_asset(client, **overrides) -> tuple[str, str]:
    # cyberlab-kali is auto-inferred as LAB-authorized (see
    # app/targets/authorization.py) so the job creation below passes the
    # authorization check without needing a manual PATCH first.
    project = (await client.post("/api/projects", json={"name": "Activity Project"})).json()
    payload = {"name": "Activity Asset", "hostname": "cyberlab-kali", "type": "CONTAINER"}
    payload.update(overrides)
    asset = (await client.post(f"/api/projects/{project['id']}/assets", json=payload)).json()
    return project["id"], asset["id"]


async def test_execute_job_records_first_and_last_seen_for_linked_asset():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        _, asset_id = await _make_project_and_target_asset(ac)
        with patch("app.api.routes.jobs.get_queue") as mock_get_queue:
            mock_get_queue.return_value = MagicMock()
            response = await ac.post("/api/jobs", json={"tool": "nmap", "target_id": asset_id})
        job_id = response.json()["id"]

    fake_result = {"stdout": "", "stderr": "", "exit_code": 0}
    with patch("app.jobs.tasks.run_tool", return_value=fake_result):
        execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        asset = session.get(Asset, asset_id)
        assert asset.first_seen is not None
        assert asset.last_seen is not None
        assert asset.last_seen == asset.first_seen
    finally:
        session.close()


async def test_execute_job_records_whatweb_technologies_on_linked_asset():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        _, asset_id = await _make_project_and_target_asset(ac)
        with patch("app.api.routes.jobs.get_queue") as mock_get_queue:
            mock_get_queue.return_value = MagicMock()
            response = await ac.post("/api/jobs", json={"tool": "whatweb", "target_id": asset_id})
        job_id = response.json()["id"]

    fake_stdout = '{"target": "http://cyberlab-kali", "plugins": {"nginx": {"version": ["1.18"]}}}'
    fake_result = {"stdout": fake_stdout, "stderr": "", "exit_code": 0}
    with patch("app.jobs.tasks.run_tool", return_value=fake_result):
        execute_job(job_id, "whatweb", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        asset = session.get(Asset, asset_id)
        assert "nginx" in asset.technologies
    finally:
        session.close()


async def test_execute_job_updates_last_seen_without_regressing_first_seen():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        _, asset_id = await _make_project_and_target_asset(ac, hostname="10.0.0.22")

    session = get_sync_session()
    try:
        earlier = datetime.now(timezone.utc) - timedelta(days=1)
        record_asset_activity(session, asset_id, earlier)
        session.commit()
        first_seen_before = session.get(Asset, asset_id).first_seen
    finally:
        session.close()

    later = datetime.now(timezone.utc)
    session = get_sync_session()
    try:
        record_asset_activity(session, asset_id, later)
        session.commit()
        asset = session.get(Asset, asset_id)
        assert asset.first_seen == first_seen_before
        assert asset.last_seen == later
    finally:
        session.close()
