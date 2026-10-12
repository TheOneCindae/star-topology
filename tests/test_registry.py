import asyncio

import pytest

from server.registry import DuplicateNodeError, NodeRegistry


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_and_unregisters():
    registry = NodeRegistry()
    reader = asyncio.StreamReader()
    writer = object()

    await registry.register(1, reader, writer)  # type: ignore[arg-type]
    with pytest.raises(DuplicateNodeError):
        await registry.register(1, reader, writer)  # type: ignore[arg-type]

    assert await registry.node_ids() == [1]
    assert await registry.unregister(1, writer) is True  # type: ignore[arg-type]
    assert await registry.count() == 0
