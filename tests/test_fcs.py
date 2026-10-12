"""
Unit tests for FCS (Frame Check Sequence) algorithms.
"""

import pytest
from protocols.fcs import (
    checksum8_compute, checksum8_validate,
    crc8_compute, crc8_validate,
    crc16_compute, crc16_validate,
    compute_fcs, validate_fcs, verify_test_vectors,
    get_fcs_name, FCSAlgorithm, FCSAlgorithmRegistry
)


class TestChecksum8:
    """Tests for 8-bit checksum algorithm."""

    def test_empty_data(self):
        fcs = checksum8_compute(b"")
        assert fcs == bytes([0x00, 0x00])

    def test_single_byte(self):
        # Sum = 0x41, checksum = -0x41 = 0xBF
        fcs = checksum8_compute(b"A")
        assert fcs == bytes([0xBF, 0x00])

    def test_known_vector_123456789(self):
        # Sum of "123456789" = 0x31+0x32+0x33+0x34+0x35+0x36+0x37+0x38+0x39
        # = 0x49 + 0x9C = 0xE5 (229)
        # checksum = -229 = 27 = 0x1B? Wait let me recalculate
        # 0x31=49, 0x32=50, 0x33=51, 0x34=52, 0x35=53, 0x36=54, 0x37=55, 0x38=56, 0x39=57
        # Sum = 49+50+51+52+53+54+55+56+57 = 477 = 0x1DD = 0xDD (mod 256)
        # -0xDD = 0x23
        # Actually: sum = 477, 477 & 0xFF = 0xDD, -0xDD & 0xFF = 0x23
        fcs = checksum8_compute(b"123456789")
        expected = bytes([0x23, 0x00])
        assert fcs == expected, f"Got {fcs.hex()}, expected {expected.hex()}"

    def test_validate_valid(self):
        data = b"test data"
        fcs = checksum8_compute(data)
        assert checksum8_validate(fcs, data) is True

    def test_validate_invalid_fcs(self):
        data = b"test data"
        fcs = checksum8_compute(data)
        bad_fcs = bytes([(fcs[0] + 1) & 0xFF, 0x00])
        assert checksum8_validate(bad_fcs, data) is False

    def test_validate_wrong_second_byte(self):
        data = b"test"
        fcs = checksum8_compute(data)
        bad_fcs = bytes([fcs[0], 0xFF])  # Second byte should be 0x00
        assert checksum8_validate(bad_fcs, data) is False

    def test_validate_wrong_length(self):
        assert checksum8_validate(b"\x00", b"test") is False
        assert checksum8_validate(b"\x00\x00\x00", b"test") is False


class TestCRC8:
    """Tests for CRC-8 algorithm (polynomial 0x07, reflected)."""

    def test_empty_data(self):
        fcs = crc8_compute(b"")
        assert fcs == bytes([0x00, 0x00])

    def test_known_vector_123456789(self):
        fcs = crc8_compute(b"123456789")
        assert fcs == bytes([0x61, 0x00]), f"Got {fcs.hex()}, expected 6100"

    def test_known_vector_AB(self):
        fcs = crc8_compute(b"AB")
        assert fcs == bytes([0x87, 0x00]), f"Got {fcs.hex()}, expected 8700"

    def test_known_vector_BA(self):
        fcs = crc8_compute(b"BA")
        assert fcs == bytes([0xB1, 0x00]), f"Got {fcs.hex()}, expected B100"

    def test_validate_valid(self):
        data = b"test data"
        fcs = crc8_compute(data)
        assert crc8_validate(fcs, data) is True

    def test_validate_invalid(self):
        data = b"test data"
        fcs = crc8_compute(data)
        bad_fcs = bytes([(fcs[0] + 1) & 0xFF, 0x00])
        assert crc8_validate(bad_fcs, data) is False

    def test_validate_wrong_second_byte(self):
        data = b"test"
        fcs = crc8_compute(data)
        bad_fcs = bytes([fcs[0], 0xFF])
        assert crc8_validate(bad_fcs, data) is False


class TestCRC16:
    """Tests for CRC-16 CCITT-FALSE algorithm."""

    def test_empty_data(self):
        fcs = crc16_compute(b"")
        assert fcs == bytes([0x00, 0x00])

    def test_known_vector_123456789(self):
        fcs = crc16_compute(b"123456789")
        assert fcs == bytes([0x31, 0xC3]), f"Got {fcs.hex()}, expected 31C3"

    def test_known_vector_AB(self):
        fcs = crc16_compute(b"AB")
        assert fcs == bytes([0x56, 0x7B]), f"Got {fcs.hex()}, expected 567B"

    def test_known_vector_BA(self):
        fcs = crc16_compute(b"BA")
        assert fcs == bytes([0x33, 0x4B]), f"Got {fcs.hex()}, expected 334B"

    def test_big_endian_output(self):
        # Verify output is big-endian
        fcs = crc16_compute(b"123456789")
        assert fcs[0] == 0x31  # High byte
        assert fcs[1] == 0xC3  # Low byte

    def test_validate_valid(self):
        data = b"test data"
        fcs = crc16_compute(data)
        assert crc16_validate(fcs, data) is True

    def test_validate_invalid(self):
        data = b"test data"
        fcs = crc16_compute(data)
        bad_fcs = bytes([(fcs[0] + 1) & 0xFF, fcs[1]])
        assert crc16_validate(bad_fcs, data) is False


class TestFCSRegistry:
    """Tests for FCS algorithm registry."""

    def test_list_algorithms(self):
        algos = FCSAlgorithmRegistry.list_algorithms()
        assert FCSAlgorithm.CHECKSUM8 in algos
        assert FCSAlgorithm.CRC8 in algos
        assert FCSAlgorithm.CRC16 in algos
        assert len(algos) == 3

    def test_get_compute(self):
        compute_fn = FCSAlgorithmRegistry.get_compute(FCSAlgorithm.CRC16)
        assert callable(compute_fn)
        result = compute_fn(b"test")
        assert len(result) == 2

    def test_get_validate(self):
        validate_fn = FCSAlgorithmRegistry.get_validate(FCSAlgorithm.CRC8)
        assert callable(validate_fn)
        data = b"test"
        fcs = compute_fcs(FCSAlgorithm.CRC8, data)
        assert validate_fn(fcs, data) is True

    def test_get_name(self):
        assert FCSAlgorithmRegistry.get_name(FCSAlgorithm.CHECKSUM8) == "Checksum-8"
        assert FCSAlgorithmRegistry.get_name(FCSAlgorithm.CRC8) == "CRC-8 (0x07)"
        assert FCSAlgorithmRegistry.get_name(FCSAlgorithm.CRC16) == "CRC-16 CCITT"

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError):
            FCSAlgorithmRegistry.get_compute("unknown")
        with pytest.raises(ValueError):
            FCSAlgorithmRegistry.get_validate("unknown")
        with pytest.raises(ValueError):
            FCSAlgorithmRegistry.get_name("unknown")


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_compute_fcs(self):
        for algo in FCSAlgorithmRegistry.list_algorithms():
            fcs = compute_fcs(algo, b"test")
            assert len(fcs) == 2

    def test_validate_fcs(self):
        for algo in FCSAlgorithmRegistry.list_algorithms():
            data = b"test data"
            fcs = compute_fcs(algo, data)
            assert validate_fcs(algo, fcs, data) is True
            # Corrupt
            bad_fcs = bytes([(fcs[0] + 1) & 0xFF, fcs[1]])
            assert validate_fcs(algo, bad_fcs, data) is False

    def test_get_fcs_name(self):
        assert get_fcs_name(FCSAlgorithm.CRC16) == "CRC-16 CCITT"


class TestTestVectors:
    """Tests for the built-in test vector verification."""

    def test_verify_test_vectors(self):
        results = verify_test_vectors()
        # All should pass
        for algo, passed in results.items():
            assert passed is True, f"{algo} test vectors failed"


class TestFCSProperties:
    """Test mathematical properties of FCS algorithms."""

    def test_checksum_commutative_for_same_bytes(self):
        # Checksum depends only on sum, so AB and BA have same checksum
        fcs_ab = checksum8_compute(b"AB")
        fcs_ba = checksum8_compute(b"BA")
        assert fcs_ab == fcs_ba

    def test_crc8_not_commutative(self):
        # CRC depends on order
        fcs_ab = crc8_compute(b"AB")
        fcs_ba = crc8_compute(b"BA")
        assert fcs_ab != fcs_ba

    def test_crc16_not_commutative(self):
        fcs_ab = crc16_compute(b"AB")
        fcs_ba = crc16_compute(b"BA")
        assert fcs_ab != fcs_ba

    def test_crc_detects_single_bit_error(self):
        data = b"Hello World"
        for algo in [FCSAlgorithm.CRC8, FCSAlgorithm.CRC16]:
            fcs = compute_fcs(algo, data)
            # Flip one bit in data
            corrupted = bytearray(data)
            corrupted[0] ^= 0x01
            assert validate_fcs(algo, fcs, bytes(corrupted)) is False

    def test_crc_detects_byte_swap(self):
        data = b"ABCD"
        for algo in [FCSAlgorithm.CRC8, FCSAlgorithm.CRC16]:
            fcs = compute_fcs(algo, data)
            # Swap two bytes
            swapped = b"BACD"
            assert validate_fcs(algo, fcs, swapped) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])