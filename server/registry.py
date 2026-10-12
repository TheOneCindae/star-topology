"""Connection registry for active client nodes."""

from dataclasses import dataclass
import asyncio
from typing import Dict, Optional


@dataclass
class ClientConnection:
    """An active client connection identified by its registered node ID."""

    node_id: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter


class DuplicateNodeError(ValueError):
    """Raised when a node ID is already registered."""


class NodeRegistry:
    """Concurrency-safe registry of active client connections."""

    def __init__(self, max_clients: int = 4) -> None:
        self._max_clients = max_clients
        self._connections: Dict[int, ClientConnection] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        node_id: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> ClientConnection:
        if not 1 <= node_id <= self._max_clients:
            raise ValueError(f"Invalid client node ID: {node_id}")
        async with self._lock:
            if node_id in self._connections:
                raise DuplicateNodeError(f"Node {node_id} is already registered")
            connection = ClientConnection(node_id, reader, writer)
            self._connections[node_id] = connection
            return connection

    async def unregister(
        self, node_id: int, writer: Optional[asyncio.StreamWriter] = None
    ) -> bool:
        async with self._lock:
            connection = self._connections.get(node_id)
            if connection is None or (
                writer is not None and connection.writer is not writer
            ):
                return False
            del self._connections[node_id]
            return True

    async def get(self, node_id: int) -> Optional[ClientConnection]:
        async with self._lock:
            return self._connections.get(node_id)

    async def count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def node_ids(self) -> list[int]:
        async with self._lock:
            return sorted(self._connections)
