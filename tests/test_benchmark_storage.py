"""
Unit tests for Benchmarking Laboratory SQLite storage and exports.
"""

import os
import tempfile
import pytest
from api.benchmark.models import (
    BenchmarkConfig,
    BenchmarkDetails,
    BenchmarkLifecycleState,
    RunMetrics,
)
from api.benchmark.storage import BenchmarkStorage
from api.benchmark.export import generate_benchmark_csv, generate_benchmark_json


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    storage = BenchmarkStorage(db_path=db_path)
    yield storage
    if os.path.exists(db_path):
        os.remove(db_path)


def test_storage_save_and_retrieve(temp_storage):
    config = BenchmarkConfig(
        name="Unit Test Experiment",
        algorithms=["round_robin", "least_connections"],
        duration=5,
        warmup_duration=1,
    )
    details = BenchmarkDetails(
        id="test-123",
        name=config.name,
        created_at="2026-10-11T12:00:00Z",
        status=BenchmarkLifecycleState.COMPLETED,
        config=config,
        elapsed_seconds=10.0,
        progress_percent=100.0,
        is_simulated=True,
        runs=[
            RunMetrics(
                algorithm="round_robin",
                repetition=1,
                total_requests=50,
                successful_requests=50,
                achieved_rps=10.0,
                mean_latency_ms=1.5,
                backend_distribution={"server1": 25, "server2": 25},
                is_simulated=True,
            )
        ],
    )

    temp_storage.save_benchmark(details)
    retrieved = temp_storage.get_benchmark("test-123")
    assert retrieved is not None
    assert retrieved.id == "test-123"
    assert retrieved.name == "Unit Test Experiment"
    assert len(retrieved.runs) == 1
    assert retrieved.runs[0].algorithm == "round_robin"
    assert retrieved.is_simulated is True

    # List
    items = temp_storage.list_benchmarks()
    assert len(items) == 1
    assert items[0].id == "test-123"

    # Export CSV
    csv_text = generate_benchmark_csv(details)
    assert "Unit Test Experiment" in csv_text
    assert "round_robin" in csv_text

    # Export JSON
    json_data = generate_benchmark_json(details)
    assert json_data["id"] == "test-123"
    assert "metadata" in json_data

    # Delete
    deleted = temp_storage.delete_benchmark("test-123")
    assert deleted is True
    assert temp_storage.get_benchmark("test-123") is None
