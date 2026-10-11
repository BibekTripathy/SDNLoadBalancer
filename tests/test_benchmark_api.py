"""
Integration tests for Benchmarking Laboratory FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_create_benchmark_validation_errors():
    # Invalid algorithm name
    res = client.post("/api/benchmarks", json={
        "name": "Invalid Algo Test",
        "algorithms": ["non_existent_algo"],
        "duration": 5,
        "warmup_duration": 1,
    })
    assert res.status_code == 422

    # Invalid warmup >= duration
    res = client.post("/api/benchmarks", json={
        "name": "Invalid Warmup Test",
        "algorithms": ["round_robin"],
        "duration": 5,
        "warmup_duration": 5,
    })
    assert res.status_code == 422

    # Invalid rate (<= 0)
    res = client.post("/api/benchmarks", json={
        "name": "Invalid Rate Test",
        "algorithms": ["round_robin"],
        "rate": 0,
        "duration": 5,
        "warmup_duration": 1,
    })
    assert res.status_code == 422


def test_start_and_query_benchmark_lifecycle():
    # Start a fast benchmark
    res = client.post("/api/benchmarks", json={
        "name": "Fast Integration Benchmark",
        "algorithms": ["round_robin"],
        "rate": 15,
        "concurrency": 2,
        "duration": 3,
        "warmup_duration": 1,
        "repetitions": 1,
    })
    assert res.status_code == 201
    data = res.json()
    b_id = data["id"]
    assert b_id is not None
    assert data["status"] in ("preparing", "running")

    # Query active
    res_active = client.get("/api/benchmarks/active")
    assert res_active.status_code == 200
    assert res_active.json()["id"] == b_id

    # Query by ID
    res_detail = client.get(f"/api/benchmarks/{b_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == b_id

    # Cancel safely
    res_cancel = client.post(f"/api/benchmarks/{b_id}/cancel")
    assert res_cancel.status_code == 200

    # Test export CSV and JSON
    res_csv = client.get(f"/api/benchmarks/{b_id}/export.csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert b_id in res_csv.text

    res_json = client.get(f"/api/benchmarks/{b_id}/export.json")
    assert res_json.status_code == 200
    assert res_json.json()["id"] == b_id

    # List
    res_list = client.get("/api/benchmarks")
    assert res_list.status_code == 200
    ids = [item["id"] for item in res_list.json()]
    assert b_id in ids
