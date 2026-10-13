"""Asyncio TCP server for client registration."""

import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from protocols.fcs import compute_fcs, validate_fcs
from protocols.frame import (
    Frame, create_ack_frame, create_config_frame, create_nack_frame, encode_frame
)
from protocols.parser import FrameParser
from protocols.mac import MACDecision, create_mac_protocol
from server.channel import Channel
from server.config import ExperimentConfig, FrameType
from server.fault_injector import FaultInjector
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
        database_path: str = ":memory:",
        authentication_required: bool = False,
        admin_token: str | None = None,
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
        self.channel = Channel(self.experiment_config.frame_duration_ms / 1000)
        self.mac = self._create_mac()
        self.faults = self._create_fault_injector()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.database = Database(database_path)
        self.authentication_required = authentication_required
        self.admin_token = admin_token or os.getenv(
            "STAR_TOPOLOGY_ADMIN_TOKEN", secrets.token_urlsafe(24)
        )
        self.event_clients: set = set()
        self._data_attempts: dict[tuple[int, int, int, bytes], int] = {}

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            await self.start()
            try:
                yield
            finally:
                await self.stop()

        self.app = FastAPI(title="Star-Topology", lifespan=lifespan)
        self.app.include_router(create_router(self), prefix="/api")
        self.app.include_router(create_websocket_router(self))
        dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
        self.app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

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

    def _create_mac(self):
        return create_mac_protocol(
            self.experiment_config.mac_protocol,
            backoff_min=self.experiment_config.backoff_min_ms / 1000,
            backoff_max=self.experiment_config.backoff_max_ms / 1000,
        )

    def _create_fault_injector(self) -> FaultInjector:
        return FaultInjector(
            self.experiment_config.frame_loss_probability,
            self.experiment_config.bit_error_rate,
            self.experiment_config.fault_seed,
        )

    def apply_config(self, config: ExperimentConfig) -> None:
        self.experiment_config = config
        self.forwarding.mode = config.forwarding_mode
        self.forwarding.fcs_algorithm = config.fcs_algorithm
        self.channel.frame_duration = config.frame_duration_ms / 1000
        self.mac = self._create_mac()
        self.faults = self._create_fault_injector()

    def _encode(self, frame: Frame) -> bytes:
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        protected += frame.payload
        return encode_frame(
            frame, compute_fcs(self.experiment_config.fcs_algorithm, protected)
        )

    async def _send_to_node(self, frame: Frame, node_id: int) -> bool:
        connection = await self.registry.get(node_id)
        if connection is None:
            return False
        try:
            connection.writer.write(self._encode(frame))
            await connection.writer.drain()
            return True
        except (ConnectionError, OSError):
            await self.registry.unregister(node_id, connection.writer)
            return False

    async def _transmit(self, frame: Frame) -> tuple[list[int], bool]:
        while True:
            decision = self.mac.decide(self.channel.busy)
            if decision is MACDecision.TRANSMIT:
                break
            self.database.record_event("mac_deferred", {
                "src": frame.src, "dst": frame.dst, "reason": decision.value,
            })
            await asyncio.sleep(
                getattr(self.mac, "last_backoff", None)
                or self.experiment_config.slot_duration_ms / 1000
            )
        self.channel.begin(frame.src)
        fault = self.faults.inject(self._encode(frame), frame.type)
        if fault.lost:
            await self._emit("frame_lost", {
                "src": frame.src, "dst": frame.dst, "seq": frame.seq,
            })
            await asyncio.sleep(self.channel.frame_duration)
            self.channel.complete(frame.src)
            return [], False
        recipients = await self.forwarding.forward(
            frame, direct=frame.type == FrameType.DATA, encoded=fault.data
        )
        if fault.corrupted:
            await self._emit("frame_corrupted", {
                "src": frame.src, "dst": frame.dst,
                "seq": frame.seq, "flipped_bits": fault.flipped_bits,
            })
        await asyncio.sleep(self.channel.frame_duration)
        if not self.channel.complete(frame.src):
            await self._emit("collision", {"src": frame.src, "dst": frame.dst})
            self.mac.record_collision()
            return recipients, False
        return recipients, not fault.corrupted

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
                        await self._emit("frame_corrupt", {
                            "src": frame.src,
                            "dst": frame.dst,
                            "seq": frame.seq,
                            "reason": "invalid_fcs",
                        })
                        continue
                    if node_id is None:
                        node_id = await self._register_hello(frame, reader, writer)
                        await self._send_config(node_id, writer)
                        continue
                    if frame.src != node_id:
                        raise ValueError(
                            f"Frame source {frame.src} does not match node {node_id}"
                        )
                    if frame.type == FrameType.DATA:
                        if not await self._authorize_data(frame):
                            await self._send_nack(writer, frame)
                            continue
                        destination = await self.registry.get(frame.dst)
                        if frame.dst == frame.src or destination is None:
                            await self._emit("transfer_denied", {
                                "src": frame.src, "dst": frame.dst,
                                "reason": "destination_not_connected",
                            })
                            await self._send_nack(writer, frame)
                            continue
                        await self._emit("transfer_approved", {
                            "src": frame.src, "dst": frame.dst, "seq": frame.seq,
                        })
                        self.database.record_message(
                            frame.src, frame.dst, frame.type, "approved"
                        )
                        key = (frame.src, frame.dst, frame.seq, frame.payload)
                        self._data_attempts[key] = self._data_attempts.get(key, 0) + 1
                        if self._data_attempts[key] > 1:
                            await self._emit("retransmission", {
                                "src": frame.src, "dst": frame.dst, "seq": frame.seq,
                            })
                        recipients, acknowledged = await self._transmit(frame)
                        if frame.dst in recipients and acknowledged:
                            ack = create_ack_frame(frame.src, 0, frame.seq)
                            if await self._send_to_node(ack, frame.src):
                                await self._emit("ack_sent", {
                                    "src": 0, "dst": frame.src, "seq": frame.seq,
                                })
                    else:
                        recipients = await self.forwarding.forward(frame)
                    await self._emit("frame_forwarded", {
                        "src": frame.src, "dst": frame.dst, "seq": frame.seq,
                        "type": frame.type, "recipients": recipients,
                    })
        except (ValueError, DuplicateNodeError) as exc:
            if node_id is None and "frame" in locals():
                await self._send_nack(writer, frame)
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
        credential = frame.payload.decode("utf-8", errors="strict")
        if self.authentication_required:
            if not credential or not self.database.authenticate_node(
                frame.src, credential
            ):
                self.database.record_audit(
                    str(frame.src), "connect", "DENY", "invalid_or_revoked_credential"
                )
                await self._send_nack(writer, frame)
                raise ValueError("Authentication failed")
        elif not self.database.nodes():
            self.database.provision_node(frame.src, name=f"Node {frame.src}")
        await self.registry.register(frame.src, reader, writer)
        await self._emit("client_connected", {"node_id": frame.src})
        return frame.src

    async def _authorize_data(self, frame: Frame) -> bool:
        if self.authentication_required and not self.database.node_is_active(frame.src):
            await self._emit("transfer_denied", {
                "src": frame.src, "dst": frame.dst, "reason": "node_not_active",
            })
            self.database.record_message(
                frame.src, frame.dst, frame.type, "denied", "node_not_active"
            )
            return False
        if not self.database.permission(frame.src, frame.dst, frame.type):
            await self._emit("transfer_denied", {
                "src": frame.src, "dst": frame.dst, "reason": "permission_denied",
            })
            self.database.record_message(
                frame.src, frame.dst, frame.type, "denied", "permission_denied"
            )
            self.database.record_audit(
                str(frame.src), "send", "DENY", "permission_denied"
            )
            return False
        return True

    async def _send_nack(self, writer: asyncio.StreamWriter, frame: Frame) -> None:
        nack = create_nack_frame(frame.src, 0, frame.seq)
        protected = bytes([nack.dst, nack.src, nack.type, nack.seq, nack.len])
        try:
            writer.write(encode_frame(
                nack, compute_fcs(self.experiment_config.fcs_algorithm, protected)
            ))
            await writer.drain()
        except (ConnectionError, OSError):
            return

    async def _send_config(
        self, node_id: int, writer: asyncio.StreamWriter
    ) -> None:
        payload = json.dumps({
            "n": node_id,
            "m": {
                "pure_aloha": 0,
                "slotted_aloha": 1,
                "csma_non_persistent": 2,
            }[self.experiment_config.mac_protocol],
            "f": {"checksum8": 0, "crc8": 1, "crc16": 2}[
                self.experiment_config.fcs_algorithm
            ],
            "a": {
                "stop_and_wait": 0,
                "go_back_n": 1,
                "selective_repeat": 2,
            }[self.experiment_config.arq_protocol],
            "i": round(self.experiment_config.traffic_interval_ms),
            "l": round(self.experiment_config.frame_loss_probability * 1000),
            "b": round(self.experiment_config.bit_error_rate * 1000),
            "t": round(self.experiment_config.arq_timeout_ms),
            "r": self.experiment_config.arq_max_retries,
        }, separators=(",", ":")).encode("ascii")
        frame = create_config_frame(node_id, payload)
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        protected += frame.payload
        fcs = compute_fcs(self.experiment_config.fcs_algorithm, protected)
        writer.write(encode_frame(frame, fcs))
        await writer.drain()
