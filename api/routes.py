"""Minimal HTTP controls and read-only experiment data."""

import json

from fastapi import APIRouter, Header, HTTPException

from server.config import ExperimentConfig


def create_router(server) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status():
        return {"clients": await server.registry.node_ids(),
                "nodes": server.database.nodes(),
                "permissions": server.database.permissions(),
                "config": server.experiment_config.to_dict(),
                "statistics": server.database.stats(),
                "mac": server.mac.stats.__dict__}

    @router.get("/events")
    async def events(limit: int = 100):
        return server.database.events(limit)

    @router.get("/messages")
    async def messages(limit: int = 100):
        return server.database.messages(limit)

    @router.get("/audit")
    async def audit(limit: int = 100):
        return server.database.audits(limit)

    @router.post("/config")
    async def config(payload: dict, x_admin_token: str | None = Header(default=None)):
        _require_admin(x_admin_token)
        try:
            config = ExperimentConfig.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        server.apply_config(config)
        return server.experiment_config.to_dict()

    def _require_admin(token: str | None) -> None:
        if not token or not __import__("hmac").compare_digest(
            token, server.admin_token
        ):
            raise HTTPException(status_code=401, detail="Admin authentication required")

    @router.post("/admin/nodes")
    async def provision_node(
        payload: dict, x_admin_token: str | None = Header(default=None)
    ):
        _require_admin(x_admin_token)
        try:
            node_id = int(payload["node_id"])
            credential = server.database.provision_node(
                node_id, str(payload.get("name") or f"Node {node_id}")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"node_id": node_id, "credential": credential}

    @router.post("/admin/nodes/{node_id}/revoke")
    async def revoke_node(node_id: int, x_admin_token: str | None = Header(default=None)):
        _require_admin(x_admin_token)
        try:
            server.database.set_node_status(node_id, "revoked")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        connection = await server.registry.get(node_id)
        if connection is not None:
            connection.writer.close()
        server.database.record_audit("admin", "revoke_node", "ALLOW", str(node_id))
        return {"node_id": node_id, "status": "revoked"}

    @router.post("/admin/nodes/{node_id}/status")
    async def set_node_status(
        node_id: int, payload: dict,
        x_admin_token: str | None = Header(default=None),
    ):
        _require_admin(x_admin_token)
        try:
            status = str(payload["status"])
            server.database.set_node_status(node_id, status)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        server.database.record_audit("admin", "set_node_status", "ALLOW", status)
        return {"node_id": node_id, "status": status}

    @router.put("/admin/permissions")
    async def set_permission(
        payload: dict, x_admin_token: str | None = Header(default=None)
    ):
        _require_admin(x_admin_token)
        try:
            source_id = int(payload["source_id"])
            destination_id = int(payload["destination_id"])
            message_type = int(payload.get("message_type", 3))
            allowed = bool(payload["allowed"])
            server.database.set_permission(
                source_id, destination_id, message_type, allowed
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        server.database.record_audit(
            "admin", "set_permission", "ALLOW", json.dumps(payload, sort_keys=True)
        )
        return {"source_id": source_id, "destination_id": destination_id,
                "message_type": message_type, "allowed": allowed}

    return router
