"""Asyncio TCP server for client registration."""

import asyncio
import json
from typing import Optional
from fastapi import FastAPI

from protocols.fcs import compute_fcs, validate_fcs
from protocols.frame import Frame, create_config_frame, encode_frame
from protocols.parser import FrameParser
from server.config import ExperimentConfig, FrameType
from server.forwarding import ForwardingEngine
from server.registry import DuplicateNodeError, NodeRegistry
from storage.database import Database
from api.routes import create_router
from api.websocket import create_websocket_router


class TCPServer:
    """Accept clients, validate HELLO frames, and maintain registrations."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        experiment_config: Optional[ExperimentConfig] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.experiment_config = experiment_config or ExperimentConfig()
        self.registry = NodeRegistry()
        self.forwarding = ForwardingEngine(
            self.registry,
            mode=self.experiment_config.forwarding_mode,
            fcs_algorithm=self.experiment_config.fcs_algorithm,
        )
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.database = Database()
        self.event_clients: set = set()
        self.app = FastAPI(title="Star-Topology")
        self.app.include_router(create_router(self), prefix="/api")
        self.app.include_router(create_websocket_router(self))

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("TCP server is not running")
        host, port = self._server.sockets[0].getsockname()[:2]
        return host, port

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("TCP server is already running")
        self._server = await asyncio.start_server(
            self._accept_client, self.host, self.port
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.database.close()

    async def _emit(self, kind: str, payload: dict) -> None:
        event = {"kind": kind, "payload": payload}
        self.database.record_event(kind, payload)
        for client in tuple(self.event_clients):
            try:
                await client.send_json(event)
            except Exception:
                self.event_clients.discard(client)

    async def _accept_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._handle_client(reader, writer)
        finally:
            if task is not None:
                self._tasks.discard(task)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        node_id: Optional[int] = None
        parser = FrameParser(
            validate_fcs_fn=lambda fcs, data: validate_fcs(
                self.experiment_config.fcs_algorithm, fcs, data
            )
        )
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    return
                result = parser.feed(data)
                if not result.frames:
                    continue
                for frame in result.frames:
                    if not frame.valid_fcs:
                        raise ValueError("Invalid FCS")
                    if node_id is None:
                        node_id = await self._register_hello(frame, reader, writer)
                        await self._send_config(node_id, writer)
                        continue
                    if frame.src != node_id:
                        raise ValueError(
                            f"Frame source {frame.src} does not match node {node_id}"
                        )
                    recipients = await self.forwarding.forward(frame)
                    await self._emit("frame_forwarded", {
                        "src": frame.src, "dst": frame.dst, "seq": frame.seq,
                        "type": frame.type, "recipients": recipients,
                    })
        except (ValueError, DuplicateNodeError):
            return
        finally:
            if node_id is not None:
                await self.registry.unregister(node_id, writer)
                await self.forwarding.forget(node_id)
                await self._emit("client_disconnected", {"node_id": node_id})
            writer.close()
            await writer.wait_closed()

    async def _register_hello(
        self,
        frame: Frame,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> int:
        if frame.type != FrameType.HELLO or frame.dst != 0:
            raise ValueError("First frame must be a HELLO addressed to the hub")
        await self.registry.register(frame.src, reader, writer)
        await self._emit("client_connected", {"node_id": frame.src})
        return frame.src

    async def _send_config(
        self, node_id: int, writer: asyncio.StreamWriter
    ) -> None:
        payload = json.dumps({"node_id": node_id}).encode("ascii")
        frame = create_config_frame(node_id, payload)
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        protected += frame.payload
        fcs = compute_fcs(self.experiment_config.fcs_algorithm, protected)
        writer.write(encode_frame(frame, fcs))
        await writer.drain()
