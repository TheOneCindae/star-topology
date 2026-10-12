"""Go-Back-N ARQ simulation with a bounded 3-bit sequence window."""

import asyncio
from typing import Any, Awaitable, Callable, Iterable

from protocols._arq import ARQResult, seq_add


class GoBackN:
    def __init__(self, window_size: int = 4, timeout: float = 0.1,
                 max_retries: int = 7, start_sequence: int = 0) -> None:
        if not 1 <= window_size <= 7 or timeout <= 0 or max_retries < 0:
            raise ValueError("window_size must be 1..7; timeout positive; retries non-negative")
        self.window_size, self.timeout, self.max_retries = window_size, timeout, max_retries
        self.sequence = start_sequence & 7

    async def send(self, packets: Iterable[Any], transmit: Callable[..., Awaitable[bool]]) -> ARQResult:
        items, result = list(packets), ARQResult()
        index = 0
        while index < len(items):
            window = items[index:index + self.window_size]
            for retry in range(self.max_retries + 1):
                result.attempts += len(window)
                replies = await asyncio.gather(*(
                    asyncio.wait_for(transmit(item, (self.sequence + offset) & 7, retry), self.timeout)
                    for offset, item in enumerate(window)
                ), return_exceptions=True)
                acknowledged = 0
                for reply in replies:
                    if reply is True:
                        acknowledged += 1
                    else:
                        break
                if acknowledged == len(window):
                    result.delivered.extend(window)
                    self.sequence = (self.sequence + len(window)) & 7
                    index += len(window)
                    break
                if retry < self.max_retries:
                    result.retransmissions += len(window) - acknowledged
            else:
                result.success = False
                result.timed_out = True
                return result
        return result

    transmit = send


GoBackNARQ = GoBackN
