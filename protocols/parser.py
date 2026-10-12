"""
Streaming frame parser for the Star-Topology Hub/Switch protocol.

This parser handles fragmented TCP reads, multiple frames in one read,
invalid markers, invalid lengths, and bounded buffering.
"""

from typing import Optional, Callable, List
from dataclasses import dataclass, field

from server.config import (
    START_MARKER, MIN_FRAME_SIZE, MAX_FRAME_SIZE, MAX_PAYLOAD_LENGTH,
    FRAME_HEADER_SIZE, FCS_SIZE
)
from protocols.frame import Frame, decode_frame


@dataclass
class ParseResult:
    """Result of a parse operation."""
    frames: List[Frame] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    bytes_consumed: int = 0


class FrameParser:
    """
    Streaming frame parser with bounded buffer and error recovery.

    The parser maintains an internal buffer that accumulates data from
    TCP reads. It extracts complete frames whenever possible, handles
    malformed data gracefully, and prevents buffer overflow.
    """

    def __init__(
        self,
        max_buffer_size: int = 1024 * 1024,  # 1 MB default
        validate_fcs_fn: Optional[Callable[[bytes, bytes], bool]] = None
    ):
        """
        Initialize the parser.

        Args:
            max_buffer_size: Maximum buffer size in bytes. Older data is
                           discarded if buffer exceeds this limit.
            validate_fcs_fn: Optional function(fcs_bytes, protected_data) -> bool
                           for FCS validation during parsing.
        """
        self._buffer = bytearray()
        self._max_buffer_size = max_buffer_size
        self._validate_fcs_fn = validate_fcs_fn
        self._parse_position = 0  # Current search position in buffer

    def feed(self, data: bytes) -> ParseResult:
        """
        Feed new data into the parser and extract complete frames.

        Args:
            data: New bytes from TCP read

        Returns:
            ParseResult with extracted frames and any errors
        """
        if not data:
            return ParseResult()

        # Append new data
        self._buffer.extend(data)

        # Enforce buffer limit - keep most recent data
        if len(self._buffer) > self._max_buffer_size:
            # Keep the last MAX_FRAME_SIZE bytes to preserve partial frames
            keep = min(MAX_FRAME_SIZE, self._max_buffer_size)
            self._buffer = self._buffer[-keep:]
            self._parse_position = 0

        result = ParseResult()

        while True:
            # Find next START marker from current parse position
            start_idx = self._find_start_marker()

            if start_idx is None:
                # No START marker found - keep buffer for next feed
                # But we can discard data before the last possible frame start
                self._discard_garbage()
                break

            if start_idx > self._parse_position:
                result.errors.append(
                    f"Invalid START marker at offset {self._parse_position}: "
                    f"0x{self._buffer[self._parse_position]:02X}"
                )
                self._parse_position = start_idx

            # Check if we have minimum frame header
            if start_idx + MIN_FRAME_SIZE > len(self._buffer):
                # Not enough data for header - wait for more
                self._parse_position = start_idx
                break

            # Peek at length field
            length = self._buffer[start_idx + 5]
            if length > MAX_PAYLOAD_LENGTH:
                # Invalid length - discard this START marker and continue
                error_msg = f"Invalid LEN at offset {start_idx}: {length} > {MAX_PAYLOAD_LENGTH}"
                result.errors.append(error_msg)
                self._parse_position = start_idx + 1
                continue

            # Calculate expected total frame size
            expected_size = MIN_FRAME_SIZE + length

            # Check if full frame is available
            if start_idx + expected_size > len(self._buffer):
                # Frame incomplete - wait for more data
                self._parse_position = start_idx
                break

            # Extract complete frame
            frame_data = bytes(self._buffer[start_idx:start_idx + expected_size])

            try:
                frame = decode_frame(frame_data, self._validate_fcs_fn)
                result.frames.append(frame)
                result.bytes_consumed += expected_size
                # Advance past this frame
                self._parse_position = start_idx + expected_size
            except ValueError as e:
                result.errors.append(f"Frame decode error at offset {start_idx}: {e}")
                # Frame decode failed - skip this START marker and continue searching
                self._parse_position = start_idx + 1

        # Compact buffer by removing consumed bytes
        self._compact_buffer(result.bytes_consumed)

        return result

    def _find_start_marker(self) -> Optional[int]:
        """Find the next START marker (0x7E) from current parse position."""
        try:
            return self._buffer.index(START_MARKER, self._parse_position)
        except ValueError:
            return None

    def _discard_garbage(self):
        """Discard garbage bytes before the last possible frame start."""
        # We can safely discard everything before the last (MAX_FRAME_SIZE - 1) bytes
        # because a valid frame cannot start earlier than that
        if len(self._buffer) > MAX_FRAME_SIZE:
            discard_count = len(self._buffer) - MAX_FRAME_SIZE + 1
            self._buffer = self._buffer[discard_count:]
            self._parse_position = max(0, self._parse_position - discard_count)

    def _compact_buffer(self, consumed: int):
        """Remove consumed bytes from the front of the buffer."""
        if consumed > 0:
            self._buffer = self._buffer[consumed:]
            self._parse_position = max(0, self._parse_position - consumed)

    def clear(self):
        """Clear the parser buffer and state."""
        self._buffer.clear()
        self._parse_position = 0

    @property
    def buffer_size(self) -> int:
        """Current buffer size in bytes."""
        return len(self._buffer)

    @property
    def has_partial_frame(self) -> bool:
        """Check if buffer contains a partial frame (START found but incomplete)."""
        start_idx = self._find_start_marker()
        if start_idx is None:
            return False
        if start_idx + MIN_FRAME_SIZE > len(self._buffer):
            return True
        length = self._buffer[start_idx + 5]
        expected_size = MIN_FRAME_SIZE + length
        return start_idx + expected_size > len(self._buffer)


def create_parser(validate_fcs_fn=None, max_buffer_size=1024*1024) -> FrameParser:
    """Factory function to create a FrameParser."""
    return FrameParser(max_buffer_size=max_buffer_size, validate_fcs_fn=validate_fcs_fn)