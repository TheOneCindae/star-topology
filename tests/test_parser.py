"""
Unit tests for the streaming frame parser.
"""

import pytest
from protocols.parser import FrameParser, create_parser
from protocols.frame import Frame, encode_frame, FrameType, HUB_ID
from protocols.fcs import compute_fcs, validate_fcs, FCSAlgorithm


def make_valid_frame(dst=0x02, src=0x01, type_=FrameType.DATA, seq=0, payload=b"", algorithm=FCSAlgorithm.CRC16):
    """Helper to create a valid encoded frame."""
    frame = Frame(dst=dst, src=src, type=type_, seq=seq, payload=payload)
    protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len]) + frame.payload
    fcs = compute_fcs(algorithm, protected)
    return encode_frame(frame, fcs), frame


class TestParserBasic:
    """Basic parser functionality tests."""

    def test_parse_single_complete_frame(self):
        parser = create_parser()
        frame_bytes, expected = make_valid_frame(payload=b"hello")

        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1
        assert len(result.errors) == 0
        assert result.frames[0].payload == b"hello"
        assert result.frames[0].valid_fcs is True

    def test_parse_multiple_frames_in_one_feed(self):
        parser = create_parser()
        frame1, _ = make_valid_frame(seq=1, payload=b"frame1")
        frame2, _ = make_valid_frame(seq=2, payload=b"frame2")
        frame3, _ = make_valid_frame(seq=3, payload=b"frame3")

        result = parser.feed(frame1 + frame2 + frame3)

        assert len(result.frames) == 3
        assert result.frames[0].seq == 1
        assert result.frames[1].seq == 2
        assert result.frames[2].seq == 3

    def test_parse_fragmented_frame(self):
        parser = create_parser()
        frame_bytes, expected = make_valid_frame(payload=b"fragmented test")

        # Feed in small chunks
        chunk_size = 3
        for i in range(0, len(frame_bytes), chunk_size):
            chunk = frame_bytes[i:i+chunk_size]
            result = parser.feed(chunk)
            # Only the last chunk should produce a frame
            if i + chunk_size >= len(frame_bytes):
                assert len(result.frames) == 1
                assert result.frames[0].payload == b"fragmented test"
            else:
                assert len(result.frames) == 0

    def test_parse_split_across_feeds(self):
        parser = create_parser()
        frame_bytes, expected = make_valid_frame(payload=b"split")

        # Feed header first
        result1 = parser.feed(frame_bytes[:6])  # Just header
        assert len(result1.frames) == 0

        # Feed rest
        result2 = parser.feed(frame_bytes[6:])
        assert len(result2.frames) == 1
        assert result2.frames[0].payload == b"split"

    def test_parse_with_garbage_before_start(self):
        parser = create_parser()
        frame_bytes, expected = make_valid_frame(payload=b"clean")

        # Prepend garbage bytes
        garbage = b"\x00\xFF\x7E\x00\x01"
        result = parser.feed(garbage + frame_bytes)

        assert len(result.frames) == 1
        assert result.frames[0].payload == b"clean"

    def test_parse_multiple_frames_with_garbage_between(self):
        parser = create_parser()
        frame1, _ = make_valid_frame(seq=1, payload=b"one")
        frame2, _ = make_valid_frame(seq=2, payload=b"two")
        garbage = b"\x00\xFF\xAA"

        result = parser.feed(frame1 + garbage + frame2)

        assert len(result.frames) == 2
        assert result.frames[0].seq == 1
        assert result.frames[1].seq == 2


class TestParserErrorHandling:
    """Test parser error handling and recovery."""

    def test_invalid_start_marker_recovery(self):
        parser = create_parser()
        frame_bytes, _ = make_valid_frame(payload=b"valid")

        # Feed byte that looks like start but isn't, then real frame
        result = parser.feed(b"\x7F" + frame_bytes)  # 0x7F != 0x7E

        assert len(result.frames) == 1
        assert result.frames[0].payload == b"valid"
        # Should have error about invalid start marker
        assert any("Invalid START marker" in e for e in result.errors)

    def test_invalid_length_recovery(self):
        parser = create_parser()
        # Frame with invalid length (100 > 64)
        bad_frame = bytes([0x7E, 0x01, 0x02, 0x03, 0x00, 100]) + b"x" * 100 + b"\x00\x00"
        good_frame, _ = make_valid_frame(payload=b"good")

        result = parser.feed(bad_frame + good_frame)

        # Should recover and parse the good frame
        assert len(result.frames) == 1
        assert result.frames[0].payload == b"good"
        assert any("Invalid LEN" in e for e in result.errors)

    def test_truncated_frame_waits_for_more_data(self):
        parser = create_parser()
        frame_bytes, _ = make_valid_frame(payload=b"truncated")

        # Feed only part of the frame
        result = parser.feed(frame_bytes[:10])  # Less than full frame
        assert len(result.frames) == 0
        assert parser.has_partial_frame

        # Feed rest
        result = parser.feed(frame_bytes[10:])
        assert len(result.frames) == 1
        assert result.frames[0].payload == b"truncated"

    def test_fcs_validation_failure_flagged(self):
        parser = create_parser(validate_fcs_fn=lambda fcs, data: validate_fcs(FCSAlgorithm.CRC16, fcs, data))
        frame_bytes, _ = make_valid_frame(payload=b"badfcs")

        # Corrupt the FCS bytes (last 2 bytes)
        corrupted = frame_bytes[:-2] + b"\xFF\xFF"

        result = parser.feed(corrupted)

        assert len(result.frames) == 1
        assert result.frames[0].valid_fcs is False
        assert result.frames[0].payload == b"badfcs"

    def test_buffer_overflow_protection(self):
        parser = create_parser(max_buffer_size=100)
        # Feed more than max buffer
        large_data = b"\x00" * 200
        result = parser.feed(large_data)

        # Buffer should be limited
        assert parser.buffer_size <= 100
        # Should not crash


class TestParserEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_feed(self):
        parser = create_parser()
        result = parser.feed(b"")
        assert len(result.frames) == 0
        assert len(result.errors) == 0

    def test_feed_after_clear(self):
        parser = create_parser()
        frame_bytes, _ = make_valid_frame(payload=b"test")

        parser.feed(frame_bytes)
        parser.clear()
        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1

    def test_minimal_frame(self):
        """Test frame with empty payload (8 bytes total)."""
        parser = create_parser()
        frame_bytes, _ = make_valid_frame(payload=b"")
        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1
        assert result.frames[0].len == 0

    def test_maximum_frame(self):
        """Test frame with maximum payload (64 bytes)."""
        parser = create_parser()
        payload = b"x" * 64
        frame_bytes, _ = make_valid_frame(payload=payload)
        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1
        assert result.frames[0].len == 64
        assert result.frames[0].payload == payload

    def test_broadcast_frame(self):
        parser = create_parser()
        frame_bytes, _ = make_valid_frame(dst=0xFF, payload=b"broadcast")
        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1
        assert result.frames[0].is_broadcast

    def test_different_frame_types(self):
        parser = create_parser()
        for type_val in [FrameType.HELLO, FrameType.CONFIG, FrameType.ACK,
                         FrameType.NACK, FrameType.JAM, FrameType.CHAN,
                         FrameType.SLOT, FrameType.STAT]:
            frame_bytes, _ = make_valid_frame(type_=type_val, payload=b"test")
            result = parser.feed(frame_bytes)
            assert len(result.frames) == 1
            assert result.frames[0].type == type_val


class TestParserFCSAlgorithms:
    """Test parser with different FCS algorithms."""

    @pytest.mark.parametrize("algorithm", [FCSAlgorithm.CHECKSUM8, FCSAlgorithm.CRC8, FCSAlgorithm.CRC16])
    def test_parse_with_different_fcs(self, algorithm):
        parser = create_parser(validate_fcs_fn=lambda fcs, data, a=algorithm: validate_fcs(a, fcs, data))
        frame_bytes, _ = make_valid_frame(payload=b"test", algorithm=algorithm)

        result = parser.feed(frame_bytes)

        assert len(result.frames) == 1
        assert result.frames[0].valid_fcs is True
        assert result.frames[0].payload == b"test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])