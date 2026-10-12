"""Shared ARQ result and sequence-space helpers."""

from dataclasses import dataclass, field
from typing import Any

SEQUENCE_MODULUS = 8


def seq_add(value: int, amount: int = 1) -> int:
    return (value + amount) & (SEQUENCE_MODULUS - 1)


def seq_distance(start: int, end: int) -> int:
    return (end - start) & (SEQUENCE_MODULUS - 1)


@dataclass
class ARQResult:
    delivered: list[Any] = field(default_factory=list)
    attempts: int = 0
    retransmissions: int = 0
    timed_out: bool = False
    success: bool = True

