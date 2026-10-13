import pytest

from protocols.selective_repeat import SelectiveRepeat


@pytest.mark.asyncio
async def test_all_acknowledgements_lost_reports_timeout():
    async def transmit(_packet: str, _sequence: int, _retry: int) -> bool:
        return False

    result = await SelectiveRepeat(max_retries=2, timeout=0.01).send(
        ["packet"], transmit
    )

    assert result.success is False
    assert result.timed_out is True
    assert result.delivered == []
