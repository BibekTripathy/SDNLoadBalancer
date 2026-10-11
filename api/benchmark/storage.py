"""
SQLite persistence storage for the SDN Benchmarking Laboratory.
Stores experiment metadata, per-repetition measurements, aggregate summaries, and time-series.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from api.benchmark.models import (
    AlgorithmSummary,
    BenchmarkConfig,
    BenchmarkDetails,
    BenchmarkLifecycleState,
    BenchmarkListItem,
    BenchmarkLiveStats,
    RunMetrics,
)

DEFAULT_DB_PATH = os.environ.get("BENCHMARK_DB_PATH", "benchmarks.db")


class BenchmarkStorage:
    """Manages SQLite persistence for benchmark experiments."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes database schema and tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    is_simulated INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    elapsed_seconds REAL DEFAULT 0,
                    progress_percent REAL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    benchmark_id TEXT NOT NULL,
                    algorithm TEXT NOT NULL,
                    repetition INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_benchmark ON benchmark_runs(benchmark_id)"
            )
            conn.commit()

    def save_benchmark(self, details: BenchmarkDetails) -> None:
        """Inserts or updates benchmark and associated run records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO benchmarks (
                    id, name, created_at, status, config_json, summary_json,
                    is_simulated, error_message, elapsed_seconds, progress_percent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    summary_json=excluded.summary_json,
                    error_message=excluded.error_message,
                    elapsed_seconds=excluded.elapsed_seconds,
                    progress_percent=excluded.progress_percent
                """,
                (
                    details.id,
                    details.name,
                    details.created_at,
                    details.status.value,
                    json.dumps(details.config.model_dump()),
                    json.dumps([s.model_dump() for s in details.summary]),
                    1 if details.is_simulated else 0,
                    details.error_message,
                    details.elapsed_seconds,
                    details.progress_percent,
                ),
            )

            # Refresh runs for this benchmark
            cursor.execute("DELETE FROM benchmark_runs WHERE benchmark_id = ?", (details.id,))
            for run in details.runs:
                cursor.execute(
                    """
                    INSERT INTO benchmark_runs (benchmark_id, algorithm, repetition, metrics_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        details.id,
                        run.algorithm,
                        run.repetition,
                        json.dumps(run.model_dump()),
                    ),
                )
            conn.commit()

    def get_benchmark(self, benchmark_id: str) -> Optional[BenchmarkDetails]:
        """Retrieves complete details for a specific benchmark by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM benchmarks WHERE id = ?", (benchmark_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "SELECT metrics_json FROM benchmark_runs WHERE benchmark_id = ? ORDER BY id ASC",
                (benchmark_id,),
            )
            run_rows = cursor.fetchall()
            runs = [RunMetrics(**json.loads(r["metrics_json"])) for r in run_rows]

            config = BenchmarkConfig(**json.loads(row["config_json"]))
            summary_raw = json.loads(row["summary_json"])
            summary = [AlgorithmSummary(**s) for s in summary_raw]

            return BenchmarkDetails(
                id=row["id"],
                name=row["name"],
                created_at=row["created_at"],
                status=BenchmarkLifecycleState(row["status"]),
                config=config,
                elapsed_seconds=row["elapsed_seconds"],
                progress_percent=row["progress_percent"],
                runs=runs,
                summary=summary,
                error_message=row["error_message"],
                is_simulated=bool(row["is_simulated"]),
            )

    def list_benchmarks(self, limit: int = 50) -> List[BenchmarkListItem]:
        """Lists historical benchmarks ordered by creation timestamp descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT b.id, b.name, b.created_at, b.status, b.config_json, b.is_simulated,
                       COUNT(r.id) AS total_runs
                FROM benchmarks b
                LEFT JOIN benchmark_runs r ON b.id = r.benchmark_id
                GROUP BY b.id
                ORDER BY b.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                cfg = json.loads(row["config_json"])
                result.append(
                    BenchmarkListItem(
                        id=row["id"],
                        name=row["name"],
                        created_at=row["created_at"],
                        status=BenchmarkLifecycleState(row["status"]),
                        algorithms=cfg.get("algorithms", []),
                        total_runs=row["total_runs"],
                        is_simulated=bool(row["is_simulated"]),
                    )
                )
            return result

    def delete_benchmark(self, benchmark_id: str) -> bool:
        """Deletes a benchmark and cascades to associated runs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM benchmarks WHERE id = ?", (benchmark_id,))
            cursor.execute("DELETE FROM benchmark_runs WHERE benchmark_id = ?", (benchmark_id,))
            conn.commit()
            return cursor.rowcount > 0


benchmark_storage = BenchmarkStorage()
