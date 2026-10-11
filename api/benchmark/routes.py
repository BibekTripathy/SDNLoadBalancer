"""
FastAPI REST routes for the SDN Benchmarking Laboratory.
"""

from typing import List
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from api.benchmark.engine import benchmark_engine
from api.benchmark.export import generate_benchmark_csv, generate_benchmark_json
from api.benchmark.models import (
    BenchmarkConfig,
    BenchmarkDetails,
    BenchmarkListItem,
)
from api.benchmark.storage import benchmark_storage

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


@router.post("", response_model=BenchmarkDetails, status_code=status.HTTP_201_CREATED)
async def create_and_start_benchmark(config: BenchmarkConfig):
    """
    Validates benchmark configuration and begins execution across selected algorithms.
    """
    try:
        details = await benchmark_engine.start_benchmark(config)
        return details
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[BenchmarkListItem])
async def list_benchmarks(limit: int = 50):
    """
    Retrieves historical benchmark experiments.
    """
    return benchmark_storage.list_benchmarks(limit=limit)


@router.get("/active", response_model=BenchmarkDetails)
async def get_active_benchmark():
    """
    Returns the currently active benchmark or latest in-memory execution status.
    """
    current = benchmark_engine.get_current_benchmark()
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active benchmark found")
    return current


@router.get("/{benchmark_id}", response_model=BenchmarkDetails)
async def get_benchmark_details(benchmark_id: str):
    """
    Retrieves detailed measurements, runs, and summaries for a specific benchmark.
    """
    # Check in-memory active first
    active = benchmark_engine.get_current_benchmark()
    if active and active.id == benchmark_id:
        return active

    item = benchmark_storage.get_benchmark(benchmark_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Benchmark '{benchmark_id}' not found")
    return item


@router.post("/{benchmark_id}/cancel")
async def cancel_benchmark(benchmark_id: str):
    """
    Safely cancels a running benchmark experiment and restores normal controller state.
    """
    success = await benchmark_engine.cancel_benchmark(benchmark_id)
    if not success:
        # Check if it was already saved in storage
        item = benchmark_storage.get_benchmark(benchmark_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Benchmark '{benchmark_id}' not found")
    return {"status": "success", "message": f"Benchmark '{benchmark_id}' cancellation requested."}


@router.get("/{benchmark_id}/export.csv")
async def export_benchmark_csv(benchmark_id: str):
    """
    Exports steady-state results and time-series for a benchmark as a downloadable CSV.
    """
    item = benchmark_storage.get_benchmark(benchmark_id)
    if not item:
        item = benchmark_engine.get_current_benchmark()
    if not item or item.id != benchmark_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")

    csv_data = generate_benchmark_csv(item)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=benchmark-{benchmark_id}.csv"},
    )


@router.get("/{benchmark_id}/export.json")
async def export_benchmark_json(benchmark_id: str):
    """
    Exports complete benchmark metadata, per-run metrics, and summaries as downloadable JSON.
    """
    item = benchmark_storage.get_benchmark(benchmark_id)
    if not item:
        item = benchmark_engine.get_current_benchmark()
    if not item or item.id != benchmark_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")

    json_data = generate_benchmark_json(item)
    return JSONResponse(
        content=json_data,
        headers={"Content-Disposition": f"attachment; filename=benchmark-{benchmark_id}.json"},
    )


@router.delete("/{benchmark_id}")
async def delete_benchmark(benchmark_id: str):
    """
    Deletes a historical benchmark experiment from persistent SQLite storage.
    """
    success = benchmark_storage.delete_benchmark(benchmark_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return {"status": "success", "message": f"Benchmark '{benchmark_id}' deleted"}
