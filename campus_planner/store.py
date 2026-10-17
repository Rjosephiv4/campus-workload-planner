"""Immutable, idempotent plan snapshots. One connection per operation."""
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from .models import PlanRequest
from .planner import ALGORITHM, schedule


class PlanStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connection() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )""")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, request: PlanRequest) -> dict:
        canonical = json.dumps(request.to_dict(), sort_keys=True, separators=(",", ":"))
        identity = hashlib.sha256((ALGORITHM + "\n" + canonical).encode()).hexdigest()
        result = {"id": identity, **schedule(request)}
        with self.connection() as connection:
            connection.execute("INSERT OR IGNORE INTO plans(id,request_json,result_json) VALUES(?,?,?)",
                               (identity, canonical, json.dumps(result, sort_keys=True)))
        return result

    def get(self, identity: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT result_json FROM plans WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def history(self, limit: int = 20) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self.connection() as connection:
            rows = connection.execute("SELECT id,created_at FROM plans ORDER BY created_at DESC,id LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
