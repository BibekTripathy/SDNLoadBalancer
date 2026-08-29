"""
Unit tests for FastAPI REST Endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from api.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"


@pytest.mark.asyncio
async def test_get_algorithms():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/controller/algorithms")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 6
    algo_ids = [item["id"] for item in data]
    assert "round_robin" in algo_ids
    assert "adaptive" in algo_ids


@pytest.mark.asyncio
async def test_switch_algorithm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/controller/algorithm", json={"algorithm": "least_bandwidth"})
    assert response.status_code == 200
    data = response.json()
    assert data["active_algorithm"] == "least_bandwidth"


@pytest.mark.asyncio
async def test_switch_invalid_algorithm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/controller/algorithm", json={"algorithm": "invalid_algo"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_servers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/controller/servers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_get_telemetry_metrics():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/telemetry/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "server1" in data


@pytest.mark.asyncio
async def test_health_override():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/health/override",
            json={"server_id": "server2", "status": "DOWN", "reason": "Testing simulated failure"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["new_state"] == "DOWN"
