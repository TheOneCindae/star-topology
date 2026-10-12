import asyncio

import pytest

from client.node_client import NodeClient
from server.tcp_server import TCPServer


@pytest.mark.asyncio
async def test_connected_destination_receives_approved_data():
    server = TCPServer()
    await server.start()
    sender = NodeClient(1, *server.address)
    receiver = NodeClient(2, *server.address)
    try:
        await sender.connect()
        await receiver.connect()
        await sender.send_data(2, b"hello")

        frame = await asyncio.wait_for(receiver.receive_frame(), timeout=1)
        assert frame.type == 0x03
        assert frame.src == 1
        assert frame.dst == 2
        assert frame.payload == b"hello"
        events = server.database.events()
        assert any(event["kind"] == "transfer_approved" for event in events)
        assert any(event["kind"] == "frame_forwarded" for event in events)
    finally:
        await sender.close()
        await receiver.close()
        await server.stop()


@pytest.mark.asyncio
async def test_disconnected_destination_is_denied():
    server = TCPServer()
    await server.start()
    sender = NodeClient(1, *server.address)
    try:
        await sender.connect()
        before = server.database.events()
        last_event_id = before[0]["id"] if before else 0
        await sender.send_data(2, b"not delivered")
        await asyncio.sleep(0.05)

        events = [
            event for event in server.database.events()
            if event["id"] > last_event_id
        ]
        denied = next(event for event in events if event["kind"] == "transfer_denied")
        assert denied["payload"] == {
            "src": 1,
            "dst": 2,
            "reason": "destination_not_connected",
        }
        assert not any(event["kind"] == "transfer_approved" for event in events)
    finally:
        await sender.close()
        await server.stop()
