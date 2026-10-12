"""
Frame Check Sequence (FCS) implementations for the Star-Topology protocol.

Implements three algorithms:
1. 8-bit Checksum (CHECKSUM8) - Two's complement sum modulo 256
2. CRC-8 (CRC8) - Polynomial 0x07, reflected, init 0x00
3. CRC-16 (CRC16) - CCITT-FALSE, polynomial 0x1021, init 0x0000

All algorithms compute FCS over the same protected fields:
DST || SRC || TYPE || SEQ || LEN || PAYLOAD
"""

from typing import Callable, Optional
from server.config import FCSAlgorithm, FCS_SIZE


# ============================================================================
# 8-bit Checksum
# ============================================================================

def checksum8_compute(data: bytes) -> bytes:
    """
    Compute 8-bit checksum (two's complement of sum modulo 256).

    Args:
        data: Protected frame bytes (DST, SRC, TYPE, SEQ, LEN, PAYLOAD)

    Returns:
        2-byte FCS: [checksum, 0x00]
    """
    total = sum(data) & 0xFF
    checksum = (-total) & 0xFF
    return bytes([checksum, 0x00])


def checksum8_validate(fcs_bytes: bytes, data: bytes) -> bool:
    """
    Validate 8-bit checksum.

    Args:
        fcs_bytes: Received 2-byte FCS
        data: Protected frame bytes

    Returns:
        True if valid, False otherwise
    """
    if len(fcs_bytes) != FCS_SIZE:
        return False
    expected = checksum8_compute(data)
    return fcs_bytes[0] == expected[0] and fcs_bytes[1] == 0x00


# ============================================================================
# CRC-8 (Polynomial 0x07, reflected)
# ============================================================================

# Pre-computed CRC-8 table for polynomial 0x07 (reflected)
# Polynomial 0x07 = x^8 + x^2 + x + 1
# Reflected polynomial = 0xE0
# This table implements the standard CRC-8 with reflected input/output
_CRC8_TABLE = [
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15,
    0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65,
    0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5,
    0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85,
    0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2,
    0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2,
    0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32,
    0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42,
    0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C,
    0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC,
    0xD1, 0xD6, 0xDF, 0xD8, 0xCD, 0xCA, 0xC3, 0xC4,
    0x39, 0x3E, 0x37, 0x30, 0x25, 0x22, 0x2B, 0x2C,
    0x11, 0x16, 0x1F, 0x18, 0x0D, 0x0A, 0x03, 0x04,
    0x59, 0x5E, 0x57, 0x50, 0x45, 0x42, 0x4B, 0x4C,
    0x71, 0x76, 0x7F, 0x78, 0x6D, 0x6A, 0x63, 0x64,
    0x1E, 0x19, 0x10, 0x17, 0x02, 0x05, 0x0C, 0x0B,
    0x26, 0x21, 0x28, 0x2F, 0x3A, 0x3D, 0x34, 0x33,
    0x4D, 0x4A, 0x43, 0x44, 0x51, 0x56, 0x5F, 0x58,
    0x75, 0x72, 0x7B, 0x7C, 0x69, 0x6E, 0x67, 0x60,
    0xFE, 0xF9, 0xF0, 0xF7, 0xE2, 0xE5, 0xEC, 0xEB,
    0xD6, 0xD1, 0xD8, 0xDF, 0xCA, 0xCD, 0xC4, 0xC3,
    0xBC, 0xBB, 0xB2, 0xB5, 0xA0, 0xA7, 0xAE, 0xA9,
    0x84, 0x83, 0x8A, 0x8D, 0x98, 0x9F, 0x96, 0x91,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B,
    0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B,
    0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB,
    0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB,
    0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3,
]


def crc8_compute(data: bytes) -> bytes:
    """
    Compute CRC-8 with polynomial 0x07 (reflected input/output).

    Args:
        data: Protected frame bytes

    Returns:
        2-byte FCS: [crc8, 0x00]
    """
    crc = 0x00
    for byte in data:
        crc = _CRC8_TABLE[crc ^ byte]
    return bytes([crc, 0x00])


def crc8_validate(fcs_bytes: bytes, data: bytes) -> bool:
    """
    Validate CRC-8.

    Args:
        fcs_bytes: Received 2-byte FCS
        data: Protected frame bytes

    Returns:
        True if valid, False otherwise
    """
    if len(fcs_bytes) != FCS_SIZE:
        return False
    expected = crc8_compute(data)
    return fcs_bytes[0] == expected[0] and fcs_bytes[1] == 0x00


# ============================================================================
# CRC-16 CCITT-FALSE (Polynomial 0x1021, non-reflected)
# ============================================================================

# Pre-computed CRC-16 table for polynomial 0x1021 (CCITT-FALSE)
# Non-reflected, MSB-first processing
_CRC16_TABLE = []
for i in range(256):
    crc = i << 8
    for _ in range(8):
        if crc & 0x8000:
            crc = (crc << 1) ^ 0x1021
        else:
            crc = crc << 1
        crc &= 0xFFFF
    _CRC16_TABLE.append(crc)


def crc16_compute(data: bytes) -> bytes:
    """
    Compute CRC-16 CCITT-FALSE (polynomial 0x1021, init 0x0000).

    Args:
        data: Protected frame bytes

    Returns:
        2-byte FCS in big-endian (network byte order)
    """
    crc = 0x0000
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC16_TABLE[((crc >> 8) ^ byte) & 0xFF]
    return crc.to_bytes(2, byteorder='big')


def crc16_validate(fcs_bytes: bytes, data: bytes) -> bool:
    """
    Validate CRC-16 CCITT-FALSE.

    Args:
        fcs_bytes: Received 2-byte FCS (big-endian)
        data: Protected frame bytes

    Returns:
        True if valid, False otherwise
    """
    if len(fcs_bytes) != FCS_SIZE:
        return False
    expected = crc16_compute(data)
    return fcs_bytes == expected


# ============================================================================
# Algorithm Registry
# ============================================================================

class FCSAlgorithmRegistry:
    """Registry of available FCS algorithms."""

    _algorithms = {
        FCSAlgorithm.CHECKSUM8: {
            'compute': checksum8_compute,
            'validate': checksum8_validate,
            'name': 'Checksum-8',
        },
        FCSAlgorithm.CRC8: {
            'compute': crc8_compute,
            'validate': crc8_validate,
            'name': 'CRC-8 (0x07)',
        },
        FCSAlgorithm.CRC16: {
            'compute': crc16_compute,
            'validate': crc16_validate,
            'name': 'CRC-16 CCITT',
        },
    }

    @classmethod
    def get_compute(cls, algorithm: str) -> Callable[[bytes], bytes]:
        """Get the compute function for an algorithm."""
        if algorithm not in cls._algorithms:
            raise ValueError(f"Unknown FCS algorithm: {algorithm}")
        return cls._algorithms[algorithm]['compute']

    @classmethod
    def get_validate(cls, algorithm: str) -> Callable[[bytes, bytes], bool]:
        """Get the validate function for an algorithm."""
        if algorithm not in cls._algorithms:
            raise ValueError(f"Unknown FCS algorithm: {algorithm}")
        return cls._algorithms[algorithm]['validate']

    @classmethod
    def get_name(cls, algorithm: str) -> str:
        """Get the display name for an algorithm."""
        if algorithm not in cls._algorithms:
            raise ValueError(f"Unknown FCS algorithm: {algorithm}")
        return cls._algorithms[algorithm]['name']

    @classmethod
    def list_algorithms(cls) -> list[str]:
        """List available algorithm identifiers."""
        return list(cls._algorithms.keys())


# Convenience functions
def compute_fcs(algorithm: str, data: bytes) -> bytes:
    """Compute FCS for the given algorithm and data."""
    return FCSAlgorithmRegistry.get_compute(algorithm)(data)


def validate_fcs(algorithm: str, fcs_bytes: bytes, data: bytes) -> bool:
    """Validate FCS for the given algorithm."""
    return FCSAlgorithmRegistry.get_validate(algorithm)(fcs_bytes, data)


def get_fcs_name(algorithm: str) -> str:
    """Get display name for algorithm."""
    return FCSAlgorithmRegistry.get_name(algorithm)


# ============================================================================
# Test Vectors (for validation)
# ============================================================================

# Known test vectors for verification
# CRC-8 of "123456789" with poly 0x07, reflected, init 0x00 = 0xF4
# CRC-16 CCITT of "123456789" = 0x29B1
# Checksum-8 of "123456789" = two's complement of sum

TEST_VECTORS = {
    'ascii_123456789': b'123456789',
    'ascii_AB': b'AB',
    'ascii_BA': b'BA',
}

EXPECTED_RESULTS = {
    'ascii_123456789': {
        FCSAlgorithm.CHECKSUM8: bytes([0x23, 0x00]),
        FCSAlgorithm.CRC8: bytes([0x61, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x31, 0xC3]),
    },
    'ascii_AB': {
        FCSAlgorithm.CHECKSUM8: bytes([0x7D, 0x00]),
        FCSAlgorithm.CRC8: bytes([0x87, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x56, 0x7B]),
    },
    'ascii_BA': {
        FCSAlgorithm.CHECKSUM8: bytes([0x7D, 0x00]),
        FCSAlgorithm.CRC8: bytes([0xB1, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x33, 0x4B]),
    },
}


def verify_test_vectors() -> dict:
    """
    Verify all test vectors against expected results.

    Returns:
        Dict with algorithm names as keys and bool (all passed) as values
    """
    results = {}
    for algo in FCSAlgorithmRegistry.list_algorithms():
        all_pass = True
        for vector_name, data in TEST_VECTORS.items():
            computed = compute_fcs(algo, data)
            expected = EXPECTED_RESULTS[vector_name][algo]
            if computed != expected:
                all_pass = False
                print(f"FAIL {algo} {vector_name}: got {computed.hex()}, expected {expected.hex()}")
            else:
                print(f"PASS {algo} {vector_name}: {computed.hex()}")
        results[algo] = all_pass
    return results


if __name__ == "__main__":
    # Run verification when executed directly
    print("Verifying FCS test vectors...")
    results = verify_test_vectors()
    print("\nSummary:")
    for algo, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {algo}: {status}")