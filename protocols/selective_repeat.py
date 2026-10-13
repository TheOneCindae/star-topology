"""Selective Repeat ARQ simulation; window is limited to half the 3-bit space."""

import asyncio
from typing import Any, Awaitable, Callable, Iterable

from protocols._arq import ARQResult


class SelectiveRepeat:
    def __init__(self, window_size: int = 4, timeout: float = 0.1,
                 max_retries: int = 7, start_sequence: int = 0) -> None:
        if not 1 <= window_size <= 4 or timeout <= 0 or max_retries < 0:
            raise ValueError("Selective Repeat window_size must be 1..4")
        self.window_size, self.timeout, self.max_retries = window_size, timeout, max_retries
        self.sequence = start_sequence & 7

    async def send(self, packets: Iterable[Any], transmit: Callable[..., Awaitable[bool]]) -> ARQResult:
        items, result = list(packets), ARQResult()
        for base in range(0, len(items), self.window_size):
            window = items[base:base + self.window_size]
            pending = set(range(len(window)))
            for retry in range(self.max_retries + 1):
                replies = await asyncio.gather(*(
                    asyncio.wait_for(transmit(window[i], (self.sequence + i) & 7, retry), self.timeout)
                    for i in sorted(pending)
                ), return_exceptions=True)
                result.attempts += len(pending)
                for i, reply in zip(sorted(pending), replies):
                    if reply is True:
                        pending.remove(i)
                if not pending:
                    result.delivered.extend(window)
                    self.sequence = (self.sequence + len(window)) & 7
                    break
                if retry < self.max_retries:
                    result.retransmissions += len(pending)
            else:
                result.success = False
                result.timed_out = True
                return result
        return result

    transmit = send


SelectiveRepeatARQ = SelectiveRepeat
