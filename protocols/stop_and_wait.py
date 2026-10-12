"""Stop-and-Wait ARQ simulation with bounded retries and 3-bit sequence IDs."""

import asyncio
from typing import Any, Awaitable, Callable, Iterable

from protocols._arq import ARQResult, seq_add

Transmit = Callable[[Any, int, int], Awaitable[bool]]


class StopAndWait:
    def __init__(self, timeout: float = 0.1, max_retries: int = 7,
                 start_sequence: int = 0) -> None:
        if timeout <= 0 or max_retries < 0:
            raise ValueError("timeout must be positive and max_retries non-negative")
        self.timeout, self.max_retries = timeout, max_retries
        self.sequence = start_sequence & 7

    async def send(self, packets: Iterable[Any], transmit: Transmit) -> ARQResult:
        result = ARQResult()
        for packet in packets:
            acknowledged = False
            for attempt in range(self.max_retries + 1):
                result.attempts += 1
                try:
                    acknowledged = await asyncio.wait_for(
                        transmit(packet, self.sequence, attempt), self.timeout)
                except asyncio.TimeoutError:
                    acknowledged = False
                if acknowledged:
                    result.delivered.append(packet)
                    self.sequence = seq_add(self.sequence)
                    break
                if attempt < self.max_retries:
                    result.retransmissions += 1
            if not acknowledged:
                result.success = False
                result.timed_out = True
                break
        return result

    transmit = send


StopAndWaitARQ = StopAndWait
