"""
Frame encoding and decoding for the Star-Topology Hub/Switch protocol.

This module provides the Frame data class and encode/decode functions.
FCS calculation is delegated to the fcs module.
"""

from dataclasses import dataclass, field
from typing import Optional
import struct

from server.config import (
    START_MARKER, MAX_PAYLOAD_LENGTH, FRAME_HEADER_SIZE, FCS_SIZE,
    MIN_FRAME_SIZE, MAX_FRAME_SIZE, FrameType, HUB_ID, CLIENT_ID_MIN,
    CLIENT_ID_MAX, BROADCAST_ID
)


@dataclass
class Frame:
    """
    Represents a parsed protocol frame.

    Attributes:
        dst: Destination node ID (0x00-0x04, 0xFF)
        src: Source node ID (0x00-0x04)
        type: Frame type (see FrameType)
        seq: Sequence number (low 3 bits used)
        payload: Application payload (0-64 bytes)
        fcs: Frame Check Sequence (2 bytes)
        valid_fcs: Whether FCS validation passed (set by decoder)
        raw: Original raw frame bytes (for debugging)
    """
    dst: int
    src: int
    type: int
    seq: int
    payload: bytes = b""
    fcs: bytes = b"\x00\x00"
    valid_fcs: bool = True
    raw: bytes = field(default=b"", repr=False)

    def __post_init__(self):
        """Validate frame fields after initialization."""
        self._validate()

    def _validate(self):
        """Validate all frame fields."""
        if not (HUB_ID <= self.dst <= CLIENT_ID_MAX or self.dst == BROADCAST_ID):
            raise ValueError(f"Invalid DST: 0x{self.dst:02X} (must be 0x00-0x04 or 0xFF)")
        if not (HUB_ID <= self.src <= CLIENT_ID_MAX):
            raise ValueError(f"Invalid SRC: 0x{self.src:02X} (must be 0x00-0x04)")
        if not FrameType.is_valid(self.type):
            raise ValueError(f"Invalid TYPE: 0x{self.type:02X}")
        if not (0 <= self.seq <= 0x07):
            raise ValueError(f"Invalid SEQ: 0x{self.seq:02X} (must be 0-7)")
        if len(self.payload) > MAX_PAYLOAD_LENGTH:
            raise ValueError(f"Payload too long: {len(self.payload)} bytes (max {MAX_PAYLOAD_LENGTH})")
        if len(self.fcs) != FCS_SIZE:
            raise ValueError(f"FCS must be {FCS_SIZE} bytes, got {len(self.fcs)}")

    @property
    def len(self) -> int:
        """Payload length (0-64)."""
        return len(self.payload)

    @property
    def total_length(self) -> int:
        """Total frame length on wire (8 + LEN)."""
        return MIN_FRAME_SIZE + self.len

    @property
    def is_broadcast(self) -> bool:
        """Check if frame is broadcast."""
        return self.dst == BROADCAST_ID

    @property
    def is_control(self) -> bool:
        """Check if frame is a control frame (not DATA)."""
        return self.type != FrameType.DATA

    def __repr__(self) -> str:
        type_name = FrameType.name(self.type)
        return (f"Frame(dst=0x{self.dst:02X}, src=0x{self.src:02X}, "
                f"type={type_name}(0x{self.type:02X}), seq={self.seq}, "
                f"len={self.len}, fcs={self.fcs.hex()}, valid_fcs={self.valid_fcs})")


def encode_frame(frame: Frame, fcs_bytes: bytes) -> bytes:
    """
    Encode a Frame object into wire-format bytes.

    Args:
        frame: Frame object (FCS field is ignored, replaced by fcs_bytes)
        fcs_bytes: 2-byte FCS computed over protected fields

    Returns:
        Complete frame bytes ready for transmission

    Raises:
        ValueError: If frame validation fails or fcs_bytes is not 2 bytes
    """
    if len(fcs_bytes) != FCS_SIZE:
        raise ValueError(f"fcs_bytes must be {FCS_SIZE} bytes, got {len(fcs_bytes)}")

    # Validate frame fields (will raise if invalid)
    frame._validate()

    # Pack header: START, DST, SRC, TYPE, SEQ, LEN
    header = struct.pack(
        "!BBBBBB",
        START_MARKER,
        frame.dst,
        frame.src,
        frame.type,
        frame.seq & 0x07,  # Ensure only low 3 bits
        frame.len
    )

    # Combine: header + payload + FCS
    return header + frame.payload + fcs_bytes


def decode_frame(data: bytes, validate_fcs_fn=None) -> Frame:
    """
    Decode wire-format bytes into a Frame object.

    Args:
        data: Complete frame bytes (must be exactly 8 + LEN bytes)
        validate_fcs_fn: Optional function(fcs_bytes, protected_data) -> bool
                        for FCS validation. If None, FCS is not validated.

    Returns:
        Frame object with valid_fcs set appropriately

    Raises:
        ValueError: If data is malformed or too short
    """
    if len(data) < MIN_FRAME_SIZE:
        raise ValueError(f"Data too short: {len(data)} bytes (min {MIN_FRAME_SIZE})")

    # Unpack header
    start, dst, src, type_, seq, length = struct.unpack("!BBBBBB", data[:FRAME_HEADER_SIZE])

    if start != START_MARKER:
        raise ValueError(f"Invalid START marker: 0x{start:02X} (expected 0x{START_MARKER:02X})")

    expected_total = MIN_FRAME_SIZE + length
    if len(data) != expected_total:
        raise ValueError(f"Length mismatch: expected {expected_total} bytes, got {len(data)}")

    if length > MAX_PAYLOAD_LENGTH:
        raise ValueError(f"Invalid LEN: {length} (max {MAX_PAYLOAD_LENGTH})")

    payload = data[FRAME_HEADER_SIZE:FRAME_HEADER_SIZE + length]
    fcs = data[FRAME_HEADER_SIZE + length:FRAME_HEADER_SIZE + length + FCS_SIZE]

    if len(fcs) != FCS_SIZE:
        raise ValueError(f"FCS truncated: got {len(fcs)} bytes")

    # Validate FCS if function provided
    valid_fcs = True
    if validate_fcs_fn is not None:
        # Protected fields: DST, SRC, TYPE, SEQ, LEN, PAYLOAD
        protected = data[1:FRAME_HEADER_SIZE + length]  # Skip START marker
        valid_fcs = validate_fcs_fn(fcs, protected)

    return Frame(
        dst=dst,
        src=src,
        type=type_,
        seq=seq & 0x07,
        payload=payload,
        fcs=fcs,
        valid_fcs=valid_fcs,
        raw=data
    )


def create_hello_frame(node_id: int) -> Frame:
    """Create a HELLO registration frame."""
    return Frame(
        dst=HUB_ID,
        src=node_id,
        type=FrameType.HELLO,
        seq=0,
        payload=b""
    )


def create_config_frame(node_id: int, config_json: bytes) -> Frame:
    """Create a CONFIG frame from hub to client."""
    if len(config_json) > MAX_PAYLOAD_LENGTH:
        raise ValueError(f"Config payload too large: {len(config_json)} bytes")
    return Frame(
        dst=node_id,
        src=HUB_ID,
        type=FrameType.CONFIG,
        seq=0,
        payload=config_json
    )


def create_data_frame(dst: int, src: int, seq: int, payload: bytes) -> Frame:
    """Create a DATA frame."""
    return Frame(
        dst=dst,
        src=src,
        type=FrameType.DATA,
        seq=seq & 0x07,
        payload=payload
    )


def create_ack_frame(dst: int, src: int, seq: int) -> Frame:
    """Create an ACK frame."""
    return Frame(
        dst=dst,
        src=src,
        type=FrameType.ACK,
        seq=seq & 0x07,
        payload=b""
    )


def create_nack_frame(dst: int, src: int, seq: int) -> Frame:
    """Create a NACK frame."""
    return Frame(
        dst=dst,
        src=src,
        type=FrameType.NACK,
        seq=seq & 0x07,
        payload=b""
    )


def create_jam_frame(collided_nodes: list[int], slot: int) -> Frame:
    """Create a JAM (collision notification) frame."""
    import json
    payload = json.dumps({"collided_nodes": collided_nodes, "slot": slot}).encode()
    return Frame(
        dst=BROADCAST_ID,
        src=HUB_ID,
        type=FrameType.JAM,
        seq=0,
        payload=payload
    )


def create_chan_frame(state: str, reserved_by: int = 0) -> Frame:
    """Create a CHAN (channel state) frame."""
    import json
    payload = json.dumps({"state": state, "reserved_by": reserved_by}).encode()
    return Frame(
        dst=BROADCAST_ID,
        src=HUB_ID,
        type=FrameType.CHAN,
        seq=0,
        payload=payload
    )


def create_slot_frame(slot_number: int, duration_ms: float) -> Frame:
    """Create a SLOT (slot boundary) frame."""
    import json
    payload = json.dumps({"slot_number": slot_number, "duration_ms": duration_ms}).encode()
    return Frame(
        dst=BROADCAST_ID,
        src=HUB_ID,
        type=FrameType.SLOT,
        seq=0,
        payload=payload
    )


def create_stat_frame(stats: dict) -> Frame:
    """Create a STAT (statistics) frame."""
    import json
    payload = json.dumps(stats).encode()
    if len(payload) > MAX_PAYLOAD_LENGTH:
        # Truncate if needed - stats are informational
        payload = payload[:MAX_PAYLOAD_LENGTH]
    return Frame(
        dst=BROADCAST_ID,
        src=HUB_ID,
        type=FrameType.STAT,
        seq=0,
        payload=payload
    )


# Sequence number arithmetic helpers
def seq_distance(a: int, b: int) -> int:
    """Forward distance from sequence a to b (0-7)."""
    return (b - a) & 0x07


def seq_add(a: int, n: int) -> int:
    """Add n to sequence a with wraparound."""
    return (a + n) & 0x07


def seq_lt(a: int, b: int, window: int = 4) -> bool:
    """
    Check if sequence a is less than b in circular sequence space.
    Assumes window <= 4 (half the modulus) for correctness.
    Returns True if b is ahead of a within the window (0 < distance <= window).
    """
    dist = seq_distance(a, b)
    return 0 < dist <= window


def seq_in_window(seq: int, base: int, window_size: int) -> bool:
    """Check if seq is in the window [base, base + window_size)."""
    return seq_distance(base, seq) < window_size