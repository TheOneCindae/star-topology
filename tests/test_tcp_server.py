import asyncio

import pytest

from client.node_client import NodeClient
from server.tcp_server import TCPServer


@pytest.mark.asyncio
async def test_client_registration_handshake():
    server = TCPServer()
    await server.start()
    client = NodeClient(1, *server.address)
    try:
        assert await client.connect() == {"node_id": 1}
        assert await server.registry.node_ids() == [1]
    finally:
        await client.close()
        await server.stop()


@pytest.mark.asyncio
async def test_duplicate_node_id_is_rejected():
    server = TCPServer()
    await server.start()
    first = NodeClient(1, *server.address)
    second = NodeClient(1, *server.address)
    try:
        assert await first.connect() == {"node_id": 1}
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(second.connect(), timeout=1)
        assert await server.registry.node_ids() == [1]
    finally:
        await first.close()
        await second.close()
        await server.stop()
