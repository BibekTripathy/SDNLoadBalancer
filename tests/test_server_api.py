"""
Integration tests for FastAPI /api/servers dynamic server pool management endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from api.main import app
from controller.config import CONFIG, BackendServer


@pytest.fixture(autouse=True)
def reset_servers():
    """Ensure standard 3 servers are in CONFIG before each test."""
    CONFIG.SERVERS = [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2, weight=1),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3, weight=2),
        BackendServer(id="server3", ip="10.0.0.4", mac="00:00:00:00:00:04", port=80, switch_port=4, weight=3),
    ]
    yield
    CONFIG.SERVERS = [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2, weight=1),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3, weight=2),
        BackendServer(id="server3", ip="10.0.0.4", mac="00:00:00:00:00:04", port=80, switch_port=4, weight=3),
    ]


@pytest.mark.asyncio
async def test_list_servers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/servers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    ids = [s["id"] for s in data]
    assert "server1" in ids
    assert "server2" in ids
    assert "server3" in ids


@pytest.mark.asyncio
async def test_suggest_server_config():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/servers/suggest")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "server4"
    assert data["ip"] == "10.0.0.5"
    assert data["switch_port"] == 5
    assert data["weight"] == 1


@pytest.mark.asyncio
async def test_get_server_details():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/servers/server1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "server1"
    assert data["ip"] == "10.0.0.2"
    assert data["switch_port"] == 2
    assert "status" in data


@pytest.mark.asyncio
async def test_get_server_details_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/servers/nonexistent_server")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_server_success():
    payload = {
        "id": "server4",
        "ip": "10.0.0.5",
        "port": 80,
        "switch_port": 5,
        "weight": 2,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "server4"
    assert data["ip"] == "10.0.0.5"
    assert data["switch_port"] == 5
    assert data["weight"] == 2

    # Check it appears in list
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        list_resp = await ac.get("/api/servers")
    ids = [s["id"] for s in list_resp.json()]
    assert "server4" in ids


@pytest.mark.asyncio
async def test_add_server_duplicate_id_rejected():
    payload = {
        "id": "server1",
        "ip": "10.0.0.99",
        "port": 80,
        "switch_port": 99,
        "weight": 1,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers", json=payload)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_server_duplicate_ip_rejected():
    payload = {
        "id": "server_dup_ip",
        "ip": "10.0.0.2",
        "port": 80,
        "switch_port": 99,
        "weight": 1,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers", json=payload)
    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_server_duplicate_switch_port_rejected():
    payload = {
        "id": "server_dup_port",
        "ip": "10.0.0.99",
        "port": 80,
        "switch_port": 2,
        "weight": 1,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers", json=payload)
    assert response.status_code == 409
    assert "already assigned" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_server_reserved_conflict():
    # Reserved client switch port 1 (schema enforces ge=2, endpoint checks reserved port)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res1 = await ac.post("/api/servers", json={
            "id": "srv_bad",
            "ip": "10.0.0.99",
            "port": 80,
            "switch_port": 1,
            "weight": 1,
        })
    assert res1.status_code in (400, 422)

    # Reserved Virtual IP (10.0.0.100)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res2 = await ac.post("/api/servers", json={
            "id": "srv_bad2",
            "ip": "10.0.0.100",
            "port": 80,
            "switch_port": 15,
            "weight": 1,
        })
    assert res2.status_code == 400


@pytest.mark.asyncio
async def test_update_server_weight():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers/server2/weight", json={"weight": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["weight"] == 5

    # Check updated in config
    assert CONFIG.get_server("server2").weight == 5


@pytest.mark.asyncio
async def test_drain_server():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/servers/server3/drain")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "draining" in data["message"].lower()


@pytest.mark.asyncio
async def test_update_server_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/servers/server1/health",
            json={"server_id": "server1", "status": "DOWN", "reason": "Simulated hardware failure"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["new_state"] == "DOWN"


@pytest.mark.asyncio
async def test_remove_server_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.delete("/api/servers/server2")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert CONFIG.get_server("server2") is None


@pytest.mark.asyncio
async def test_remove_server_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.delete("/api/servers/nonexistent_server")
    assert response.status_code == 404
