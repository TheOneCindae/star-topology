"""
Unit tests for frame encoding/decoding.
"""

import pytest
from protocols.frame import (
    Frame, encode_frame, decode_frame,
    create_hello_frame, create_config_frame, create_data_frame,
    create_ack_frame, create_nack_frame,
    seq_distance, seq_add, seq_lt, seq_in_window,
    FrameType, HUB_ID, BROADCAST_ID, MAX_PAYLOAD_LENGTH
)
from protocols.fcs import compute_fcs, validate_fcs, FCSAlgorithm


class TestFrameCreation:
    """Test Frame object creation and validation."""

    def test_valid_data_frame(self):
        frame = Frame(dst=0x02, src=0x01, type=FrameType.DATA, seq=3, payload=b"hello")
        assert frame.dst == 0x02
        assert frame.src == 0x01
        assert frame.type == FrameType.DATA
        assert frame.seq == 3
        assert frame.payload == b"hello"
        assert frame.len == 5

    def test_empty_payload(self):
        frame = Frame(dst=0x01, src=0x02, type=FrameType.ACK, seq=0, payload=b"")
        assert frame.len == 0
        assert frame.total_length == 8  # MIN_FRAME_SIZE

    def test_max_payload(self):
        payload = b"x" * MAX_PAYLOAD_LENGTH
        frame = Frame(dst=0x01, src=0x02, type=FrameType.DATA, seq=0, payload=payload)
        assert frame.len == MAX_PAYLOAD_LENGTH
        assert frame.total_length == 8 + MAX_PAYLOAD_LENGTH

    def test_invalid_dst(self):
        with pytest.raises(ValueError):
            Frame(dst=0x05, src=0x01, type=FrameType.DATA, seq=0, payload=b"")

    def test_invalid_src(self):
        with pytest.raises(ValueError):
            Frame(dst=0x01, src=0x05, type=FrameType.DATA, seq=0, payload=b"")

    def test_broadcast_dst_valid(self):
        frame = Frame(dst=BROADCAST_ID, src=0x01, type=FrameType.DATA, seq=0, payload=b"")
        assert frame.is_broadcast

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            Frame(dst=0x01, src=0x02, type=0xFF, seq=0, payload=b"")

    def test_invalid_seq(self):
        with pytest.raises(ValueError):
            Frame(dst=0x01, src=0x02, type=FrameType.DATA, seq=8, payload=b"")

    def test_payload_too_long(self):
        with pytest.raises(ValueError):
            Frame(dst=0x01, src=0x02, type=FrameType.DATA, seq=0, payload=b"x" * (MAX_PAYLOAD_LENGTH + 1))

    def test_fcs_length_validation(self):
        with pytest.raises(ValueError):
            Frame(dst=0x01, src=0x02, type=FrameType.DATA, seq=0, payload=b"", fcs=b"\x00")


class TestFrameEncodeDecode:
    """Test frame encoding and decoding round-trip."""

    def test_encode_decode_roundtrip(self):
        frame = Frame(dst=0x02, src=0x01, type=FrameType.DATA, seq=5, payload=b"test payload")
        # Protected fields: DST, SRC, TYPE, SEQ, LEN, PAYLOAD
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len]) + frame.payload
        fcs = compute_fcs(FCSAlgorithm.CRC16, protected)
        encoded = encode_frame(frame, fcs)
        decoded = decode_frame(encoded, validate_fcs_fn=lambda fcs_bytes, data: validate_fcs(FCSAlgorithm.CRC16, fcs_bytes, data))

        assert decoded.dst == frame.dst
        assert decoded.src == frame.src
        assert decoded.type == frame.type
        assert decoded.seq == frame.seq
        assert decoded.payload == frame.payload
        assert decoded.valid_fcs is True

    def test_encode_decode_empty_payload(self):
        frame = Frame(dst=0x01, src=0x02, type=FrameType.ACK, seq=0, payload=b"")
        fcs = compute_fcs(FCSAlgorithm.CRC16, bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len]) + frame.payload)
        encoded = encode_frame(frame, fcs)
        decoded = decode_frame(encoded, validate_fcs_fn=lambda fcs_bytes, data: validate_fcs(FCSAlgorithm.CRC16, fcs_bytes, data))

        assert decoded.len == 0
        assert decoded.payload == b""
        assert decoded.valid_fcs is True

    def test_encode_decode_max_payload(self):
        payload = b"x" * MAX_PAYLOAD_LENGTH
        frame = Frame(dst=0x01, src=0x02, type=FrameType.DATA, seq=7, payload=payload)
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len]) + frame.payload
        fcs = compute_fcs(FCSAlgorithm.CRC16, protected)
        encoded = encode_frame(frame, fcs)

        assert len(encoded) == 8 + MAX_PAYLOAD_LENGTH
        decoded = decode_frame(encoded, validate_fcs_fn=lambda fcs_bytes, data: validate_fcs(FCSAlgorithm.CRC16, fcs_bytes, data))
        assert decoded.payload == payload
        assert decoded.valid_fcs is True

    def test_decode_invalid_start_marker(self):
        # Valid frame structure but wrong START marker
        bad_frame = bytes([0x7F, 0x01, 0x02, 0x03, 0x00, 0x00, 0x00, 0x00])
        with pytest.raises(ValueError, match="Invalid START marker"):
            decode_frame(bad_frame)

    def test_decode_invalid_length(self):
        # Length says 100 but max is 64
        bad_frame = bytes([0x7E, 0x01, 0x02, 0x03, 0x00, 100]) + b"x" * 100 + b"\x00\x00"
        with pytest.raises(ValueError, match="Invalid LEN"):
            decode_frame(bad_frame)

    def test_decode_truncated_frame(self):
        # Header says 10 bytes payload but only 5 provided
        bad_frame = bytes([0x7E, 0x01, 0x02, 0x03, 0x00, 10]) + b"xxxxx" + b"\x00\x00"
        with pytest.raises(ValueError, match="Length mismatch"):
            decode_frame(bad_frame)

    def test_decode_fcs_validation_failure(self):
        frame = Frame(dst=0x02, src=0x01, type=FrameType.DATA, seq=1, payload=b"data")
        # Corrupt the FCS
        bad_fcs = b"\xFF\xFF"
        encoded = encode_frame(frame, bad_fcs)
        decoded = decode_frame(encoded, validate_fcs_fn=lambda fcs_bytes, data: validate_fcs(FCSAlgorithm.CRC16, fcs_bytes, data))
        assert decoded.valid_fcs is False

    def test_decode_without_fcs_validation(self):
        frame = Frame(dst=0x02, src=0x01, type=FrameType.DATA, seq=1, payload=b"data")
        bad_fcs = b"\xFF\xFF"
        encoded = encode_frame(frame, bad_fcs)
        # No validation function provided
        decoded = decode_frame(encoded, validate_fcs_fn=None)
        assert decoded.valid_fcs is True  # Not validated


class TestFrameFactoryFunctions:
    """Test frame factory helper functions."""

    def test_create_hello_frame(self):
        frame = create_hello_frame(0x01)
        assert frame.dst == HUB_ID
        assert frame.src == 0x01
        assert frame.type == FrameType.HELLO
        assert frame.seq == 0
        assert frame.payload == b""

    def test_create_config_frame(self):
        config = b'{"test": "config"}'
        frame = create_config_frame(0x02, config)
        assert frame.dst == 0x02
        assert frame.src == HUB_ID
        assert frame.type == FrameType.CONFIG
        assert frame.payload == config

    def test_create_data_frame(self):
        frame = create_data_frame(0x02, 0x01, 3, b"hello")
        assert frame.dst == 0x02
        assert frame.src == 0x01
        assert frame.type == FrameType.DATA
        assert frame.seq == 3
        assert frame.payload == b"hello"

    def test_create_ack_frame(self):
        frame = create_ack_frame(0x01, 0x02, 5)
        assert frame.type == FrameType.ACK
        assert frame.seq == 5
        assert frame.payload == b""

    def test_create_nack_frame(self):
        frame = create_nack_frame(0x01, 0x02, 5)
        assert frame.type == FrameType.NACK
        assert frame.seq == 5


class TestSequenceArithmetic:
    """Test sequence number arithmetic with wraparound."""

    def test_seq_distance_basic(self):
        assert seq_distance(0, 1) == 1
        assert seq_distance(1, 3) == 2
        assert seq_distance(0, 7) == 7

    def test_seq_distance_wraparound(self):
        assert seq_distance(7, 0) == 1
        assert seq_distance(6, 1) == 3
        assert seq_distance(5, 2) == 5

    def test_seq_add(self):
        assert seq_add(0, 1) == 1
        assert seq_add(7, 1) == 0
        assert seq_add(6, 3) == 1

    def test_seq_lt(self):
        # Normal ordering
        assert seq_lt(0, 1) is True
        assert seq_lt(1, 3) is True
        assert seq_lt(0, 2) is True
        assert seq_lt(0, 3) is True
        assert seq_lt(0, 4) is True  # distance 4 == window
        assert seq_lt(0, 5) is False  # distance 5 > window
        assert seq_lt(0, 7) is False  # distance 7 > window
        assert seq_lt(2, 0) is False

    def test_seq_lt_wraparound(self):
        # 7 comes before 1 (distance 2)
        assert seq_lt(7, 1) is True
        assert seq_lt(7, 2) is True
        assert seq_lt(7, 3) is True  # distance 4 == window
        assert seq_lt(7, 4) is False  # distance 5 > window

    def test_seq_in_window(self):
        assert seq_in_window(0, 0, 4) is True
        assert seq_in_window(1, 0, 4) is True
        assert seq_in_window(3, 0, 4) is True
        assert seq_in_window(4, 0, 4) is False  # Not in [0, 4)
        assert seq_in_window(7, 0, 4) is False

    def test_seq_in_window_wraparound(self):
        # Window [6, 10) = [6, 7, 0, 1] (mod 8)
        assert seq_in_window(6, 6, 4) is True
        assert seq_in_window(7, 6, 4) is True
        assert seq_in_window(0, 6, 4) is True
        assert seq_in_window(1, 6, 4) is True
        assert seq_in_window(2, 6, 4) is False


class TestFrameTypeConstants:
    """Test FrameType constants and helpers."""

    def test_frame_type_values(self):
        assert FrameType.HELLO == 0x01
        assert FrameType.CONFIG == 0x02
        assert FrameType.DATA == 0x03
        assert FrameType.ACK == 0x04
        assert FrameType.NACK == 0x05
        assert FrameType.JAM == 0x06
        assert FrameType.CHAN == 0x07
        assert FrameType.SLOT == 0x08
        assert FrameType.STAT == 0x09

    def test_frame_type_is_valid(self):
        assert FrameType.is_valid(FrameType.DATA) is True
        assert FrameType.is_valid(0xFF) is False

    def test_frame_type_name(self):
        assert FrameType.name(FrameType.DATA) == "DATA"
        assert FrameType.name(0xFF) == "UNKNOWN(0xFF)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])