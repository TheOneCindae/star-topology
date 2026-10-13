"""Application-layer shared channel and collision tracking."""

from dataclasses import dataclass
import time
from typing import Callable, Dict, Optional


@dataclass
class Transmission:
    """A transmission currently occupying the shared channel."""

    node_id: int
    started_at: float
    ends_at: float
    collided: bool = False


class Channel:
    """Deterministic channel model for MAC protocol experiments."""

    def __init__(
        self,
        frame_duration: float = 0.01,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if frame_duration <= 0:
            raise ValueError("frame_duration must be positive")
        self.frame_duration = frame_duration
        self._clock = clock
        self._active: Dict[int, Transmission] = {}
        self.collision_count = 0

    @property
    def busy(self) -> bool:
        self._expire()
        return bool(self._active)

    @property
    def active_transmissions(self) -> tuple[Transmission, ...]:
        self._expire()
        return tuple(self._active.values())

    def begin(self, node_id: int, now: Optional[float] = None) -> Transmission:
        """Start a transmission and mark it collided if another is active."""
        start = self._clock() if now is None else now
        self._expire(start)
        if self._active:
            self.collision_count += 1
            for active in self._active.values():
                active.collided = True
        transmission = Transmission(node_id, start, start + self.frame_duration)
        self._active[node_id] = transmission
        return transmission

    def complete(self, node_id: int, now: Optional[float] = None) -> bool:
        """End a transmission and report whether it completed without collision."""
        current = self._clock() if now is None else now
        transmission = self._active.pop(node_id, None)
        if transmission is None:
            return False
        return current >= transmission.ends_at and not transmission.collided

    def _expire(self, now: Optional[float] = None) -> None:
        current = self._clock() if now is None else now
        for node_id, transmission in tuple(self._active.items()):
            if current >= transmission.ends_at:
                del self._active[node_id]
