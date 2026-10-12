"""Medium-access-control decisions for the shared application channel."""

from dataclasses import dataclass
from enum import Enum
import random
from typing import Optional

from server.config import MACProtocol


class MACDecision(str, Enum):
    """Action a node should take for a queued frame."""

    TRANSMIT = "transmit"
    DEFER = "defer"
    WAIT_FOR_SLOT = "wait_for_slot"


@dataclass
class MACStats:
    """Counters useful for comparing MAC protocols."""

    attempts: int = 0
    transmissions: int = 0
    deferrals: int = 0
    collisions: int = 0


class MACProtocolEngine:
    """Base interface for deterministic MAC decision engines."""

    protocol: str

    def __init__(self) -> None:
        self.stats = MACStats()

    def decide(
        self, channel_busy: bool, *, slot_boundary: bool = True
    ) -> MACDecision:
        raise NotImplementedError

    def record_collision(self) -> None:
        self.stats.collisions += 1


class PureALOHA(MACProtocolEngine):
    """Pure ALOHA transmits immediately whenever a frame is queued."""

    protocol = MACProtocol.PURE_ALOHA

    def decide(self, channel_busy: bool, *, slot_boundary: bool = True) -> MACDecision:
        self.stats.attempts += 1
        self.stats.transmissions += 1
        return MACDecision.TRANSMIT


class SlottedALOHA(MACProtocolEngine):
    """Slotted ALOHA transmits only at a slot boundary."""

    protocol = MACProtocol.SLOTTED_ALOHA

    def decide(self, channel_busy: bool, *, slot_boundary: bool = True) -> MACDecision:
        self.stats.attempts += 1
        if not slot_boundary:
            self.stats.deferrals += 1
            return MACDecision.WAIT_FOR_SLOT
        self.stats.transmissions += 1
        return MACDecision.TRANSMIT


class NonPersistentCSMA(MACProtocolEngine):
    """CSMA defers a busy-channel attempt using a random backoff."""

    protocol = MACProtocol.CSMA_NON_PERSISTENT

    def __init__(
        self,
        backoff_min: float = 0.005,
        backoff_max: float = 0.05,
        rng: Optional[random.Random] = None,
    ) -> None:
        super().__init__()
        if backoff_min < 0 or backoff_max < backoff_min:
            raise ValueError("Invalid CSMA backoff range")
        self.backoff_min = backoff_min
        self.backoff_max = backoff_max
        self.rng = rng or random.Random()
        self.last_backoff: Optional[float] = None

    def decide(self, channel_busy: bool, *, slot_boundary: bool = True) -> MACDecision:
        self.stats.attempts += 1
        if channel_busy:
            self.last_backoff = self.rng.uniform(
                self.backoff_min, self.backoff_max
            )
            self.stats.deferrals += 1
            return MACDecision.DEFER
        self.last_backoff = None
        self.stats.transmissions += 1
        return MACDecision.TRANSMIT


def create_mac_protocol(
    protocol: str,
    *,
    backoff_min: float = 0.005,
    backoff_max: float = 0.05,
    rng: Optional[random.Random] = None,
) -> MACProtocolEngine:
    """Create a MAC engine from the configured protocol identifier."""
    if protocol == MACProtocol.PURE_ALOHA:
        return PureALOHA()
    if protocol == MACProtocol.SLOTTED_ALOHA:
        return SlottedALOHA()
    if protocol == MACProtocol.CSMA_NON_PERSISTENT:
        return NonPersistentCSMA(backoff_min, backoff_max, rng)
    raise ValueError(f"Unknown MAC protocol: {protocol}")
