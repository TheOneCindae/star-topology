import asyncio

import pytest

from client.node_client import NodeClient
from server.tcp_server import TCPServer


@pytest.mark.asyncio
async def test_invalid_credential_is_rejected():
    server = TCPServer(authentication_required=True)
    credential = server.database.provision_node(1)
    await server.start()
    invalid = NodeClient(1, *server.address, credential="wrong")
    valid = NodeClient(1, *server.address, credential=credential)
    try:
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(invalid.connect(), timeout=1)
        assert await valid.connect() == {"node_id": 1}
    finally:
        await invalid.close()
        await valid.close()
        await server.stop()


@pytest.mark.asyncio
async def test_acl_denies_transfer_and_revocation_blocks_connected_node():
    server = TCPServer(authentication_required=True)
    sender_credential = server.database.provision_node(1)
    receiver_credential = server.database.provision_node(2)
    server.database.set_permission(1, 2, 3, False)
    await server.start()
    sender = NodeClient(1, *server.address, credential=sender_credential)
    receiver = NodeClient(2, *server.address, credential=receiver_credential)
    try:
        await sender.connect()
        await receiver.connect()
        result = await sender.send_data(2, b"blocked")
        assert result.success is False
        assert not any(
            event["kind"] == "transfer_approved"
            for event in server.database.events()
        )
        server.database.set_node_status(1, "revoked")
        result = await sender.send_data(2, b"revoked")
        assert result.success is False
        assert any(
            event["payload"].get("reason") == "node_not_active"
            for event in server.database.events()
            if event["kind"] == "transfer_denied"
        )
    finally:
        await sender.close()
        await receiver.close()
        await server.stop()
