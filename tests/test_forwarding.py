import asyncio

import pytest

from protocols.frame import Frame, FrameType
from server.config import BROADCAST_ID, ForwardingMode
from server.forwarding import ForwardingEngine
from server.registry import NodeRegistry


class FakeWriter:
    def __init__(self):
        self.frames: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.frames.append(data)

    async def drain(self) -> None:
        return None


async def make_registry(node_ids: list[int]):
    registry = NodeRegistry()
    writers = {}
    for node_id in node_ids:
        writer = FakeWriter()
        writers[node_id] = writer
        await registry.register(node_id, asyncio.StreamReader(), writer)  # type: ignore[arg-type]
    return registry, writers


@pytest.mark.asyncio
async def test_hub_forwards_unicast_to_all_other_nodes():
    registry, writers = await make_registry([1, 2, 3])
    engine = ForwardingEngine(registry)
    frame = Frame(dst=2, src=1, type=FrameType.DATA, seq=0, payload=b"hello")

    assert await engine.forward(frame) == [2, 3]
    assert writers[1].frames == []
    assert len(writers[2].frames) == 1
    assert len(writers[3].frames) == 1


@pytest.mark.asyncio
async def test_hub_broadcast_excludes_source():
    registry, writers = await make_registry([1, 2, 3])
    engine = ForwardingEngine(registry)
    frame = Frame(dst=BROADCAST_ID, src=1, type=FrameType.DATA, seq=0, payload=b"all")

    assert await engine.forward(frame) == [2, 3]
    assert writers[1].frames == []


@pytest.mark.asyncio
async def test_switch_learns_sources_and_forwards_known_destination_only():
    registry, writers = await make_registry([1, 2, 3])
    engine = ForwardingEngine(registry, mode=ForwardingMode.SWITCH)
    learn = Frame(dst=2, src=1, type=FrameType.DATA, seq=0, payload=b"learn")
    reply = Frame(dst=1, src=2, type=FrameType.DATA, seq=0, payload=b"reply")

    assert await engine.forward(learn) == [2, 3]
    assert await engine.forward(reply) == [1]
    assert len(writers[1].frames) == 1
    assert len(writers[2].frames) == 1
    assert len(writers[3].frames) == 1
    assert await engine.learned_nodes() == [1, 2]


@pytest.mark.asyncio
async def test_switch_ages_entries():
    registry, _ = await make_registry([1, 2])
    now = [0.0]
    engine = ForwardingEngine(
        registry, mode=ForwardingMode.SWITCH, aging_seconds=10, clock=lambda: now[0]
    )
    frame = Frame(dst=2, src=1, type=FrameType.DATA, seq=0, payload=b"learn")

    await engine.forward(frame)
    assert await engine.learned_nodes() == [1]
    now[0] = 10.0
    assert await engine.learned_nodes() == []
