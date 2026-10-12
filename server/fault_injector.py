"""Deterministic, DATA-only loss and bit corruption for experiments."""

from dataclasses import dataclass
import random
from typing import Optional

from server.config import FrameType


@dataclass(frozen=True)
class FaultInjectionResult:
    """The explicit outcome of applying faults to one encoded frame."""

    delivered: bool
    data: Optional[bytes]
    lost: bool
    corrupted: bool
    flipped_bits: int = 0


class FaultInjector:
    """Apply configured faults without ever modifying control frames."""

    def __init__(self, loss_probability: float = 0.0, bit_error_rate: float = 0.0,
                 seed: Optional[int] = None) -> None:
        if not 0 <= loss_probability <= 1 or not 0 <= bit_error_rate <= 1:
            raise ValueError("fault probabilities must be in [0, 1]")
        self.loss_probability = loss_probability
        self.bit_error_rate = bit_error_rate
        self.seed = seed
        self._rng = random.Random(seed)

    def inject(self, encoded: bytes, frame_type: Optional[int] = None) -> FaultInjectionResult:
        """Return a result; ``data`` is None only when the frame is lost."""
        if frame_type is None:
            frame_type = encoded[3] if len(encoded) > 3 else FrameType.DATA
        if frame_type != FrameType.DATA:
            return FaultInjectionResult(True, encoded, False, False)
        if self._rng.random() < self.loss_probability:
            return FaultInjectionResult(False, None, True, False)
        data = bytearray(encoded)
        flips = 0
        # START/header are transport metadata; payload and FCS are faulted.
        for index in range(6, len(data)):
            for bit in range(8):
                if self._rng.random() < self.bit_error_rate:
                    data[index] ^= 1 << bit
                    flips += 1
        return FaultInjectionResult(True, bytes(data), False, flips > 0, flips)

    def reset(self) -> None:
        """Reset the stream to its original seed, useful for repeatable runs."""
        self._rng.seed(self.seed)

    inject_frame = inject
