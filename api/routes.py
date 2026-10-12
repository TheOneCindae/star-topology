"""Minimal HTTP controls and read-only experiment data."""

from fastapi import APIRouter, HTTPException

from server.config import ExperimentConfig


def create_router(server) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status():
        return {"clients": await server.registry.node_ids(),
                "config": server.experiment_config.to_dict()}

    @router.get("/events")
    async def events(limit: int = 100):
        return server.database.events(limit)

    @router.post("/config")
    async def config(payload: dict):
        try:
            server.experiment_config = ExperimentConfig.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return server.experiment_config.to_dict()

    return router
