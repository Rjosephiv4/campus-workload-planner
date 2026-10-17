"""Optional localhost HTTP adapter. Add authentication before public deployment."""
from contextlib import asynccontextmanager
import os
import sqlite3
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from .models import InputError, PlanRequest
from .store import PlanStore


def create_app(database: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = PlanStore(database or os.environ.get("CAMPUS_PLAN_DB", "plans.sqlite3"))
        yield

    app = FastAPI(title="Campus Workload Planner", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Plan storage is unavailable"})

    @app.get("/health")
    def health():
        app.state.store.history(1)
        return {"status": "ok"}

    @app.post("/v1/plans")
    def create_plan(payload: dict):
        """Submit now, tasks, and availability. Repeating the same input returns the same ID."""
        try:
            request = PlanRequest.parse(payload)
        except InputError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return app.state.store.create(request)

    @app.get("/v1/plans")
    def history(limit: int = Query(default=20, ge=1, le=100)):
        return app.state.store.history(limit)

    @app.get("/v1/plans/{identity}")
    def get_plan(identity: str):
        result = app.state.store.get(identity)
        if result is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        return result

    return app


app = create_app()
