"""Hub and learning-switch forwarding for validated protocol frames."""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from protocols.fcs import compute_fcs
from protocols.frame import Frame, encode_frame
from server.config import BROADCAST_ID, FCSAlgorithm, ForwardingMode
from server.registry import ClientConnection, NodeRegistry


@dataclass
class ForwardingEntry:
    """A learned source node and the time it was last observed."""

    node_id: int
    connection: ClientConnection
    last_seen: float


class ForwardingEngine:
    """Forward frames using hub flooding or switch learning."""

    def __init__(
        self,
        registry: NodeRegistry,
        mode: str = ForwardingMode.HUB,
        fcs_algorithm: str = FCSAlgorithm.CRC16,
        aging_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not ForwardingMode.is_valid(mode):
            raise ValueError(f"Invalid forwarding mode: {mode}")
        if aging_seconds < 0:
            raise ValueError("aging_seconds must be non-negative")
        self.registry = registry
        self.mode = mode
        self.fcs_algorithm = fcs_algorithm
        self.aging_seconds = aging_seconds
        self._clock = clock
        self._table: Dict[int, ForwardingEntry] = {}
        self._lock = asyncio.Lock()

    async def forward(self, frame: Frame) -> list[int]:
        """Forward a frame and return the node IDs that received it."""
        recipients = await self._select_recipients(frame)
        wire_frame = self._encode(frame)
        delivered: list[int] = []
        for connection in recipients:
            try:
                connection.writer.write(wire_frame)
                await connection.writer.drain()
            except (ConnectionError, OSError):
                await self.registry.unregister(connection.node_id, connection.writer)
                continue
            delivered.append(connection.node_id)
        return delivered

    async def forget(self, node_id: int) -> None:
        """Remove a node from the learned switch table."""
        async with self._lock:
            self._table.pop(node_id, None)

    async def learned_nodes(self) -> list[int]:
        """Return currently learned switch node IDs after aging entries."""
        async with self._lock:
            self._purge_expired()
            return sorted(self._table)

    async def _select_recipients(self, frame: Frame) -> list[ClientConnection]:
        connections = [
            connection
            for node_id in await self.registry.node_ids()
            if (connection := await self.registry.get(node_id)) is not None
            and node_id != frame.src
        ]
        if self.mode == ForwardingMode.HUB:
            return connections

        now = self._clock()
        async with self._lock:
            self._purge_expired(now)
            source = await self.registry.get(frame.src)
            if source is not None:
                self._table[frame.src] = ForwardingEntry(frame.src, source, now)

            if frame.dst == BROADCAST_ID:
                return connections

            learned = self._table.get(frame.dst)
            if learned is None:
                return connections
            if learned.connection.node_id == frame.src:
                return []
            return [learned.connection]

    def _purge_expired(self, now: Optional[float] = None) -> None:
        current = self._clock() if now is None else now
        expired = [
            node_id
            for node_id, entry in self._table.items()
            if current - entry.last_seen >= self.aging_seconds
        ]
        for node_id in expired:
            del self._table[node_id]

    def _encode(self, frame: Frame) -> bytes:
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        protected += frame.payload
        fcs = compute_fcs(self.fcs_algorithm, protected)
        return encode_frame(frame, fcs)
