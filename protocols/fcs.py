"""
Frame Check Sequence (FCS) implementations for the Star-Topology protocol.

Implements three algorithms:
1. 8-bit Checksum (CHECKSUM8) - Two's complement sum modulo 256
2. CRC-8 (CRC8) - Polynomial 0x07, reflected, init 0x00
3. CRC-16 (CRC16) - CCITT-FALSE, polynomial 0x1021, init 0xFFFF

All algorithms compute FCS over the same protected fields:
DST || SRC || TYPE || SEQ || LEN || PAYLOAD
"""

from typing import Callable
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
# CRC-8 (Polynomial 0x07, non-reflected)
# ============================================================================

# The table is generated below so it cannot drift from the polynomial.

def _build_crc8_table() -> list[int]:
    """Build the non-reflected CRC-8 table for polynomial 0x07."""
    table: list[int] = []
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    return table


_CRC8_TABLE = _build_crc8_table()

def crc8_compute(data: bytes) -> bytes:
    """
    Compute CRC-8 with polynomial 0x07 (non-reflected).

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
    crc = 0xFFFF
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
        FCSAlgorithm.CRC8: bytes([0xF4, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x29, 0xB1]),
    },
    'ascii_AB': {
        FCSAlgorithm.CHECKSUM8: bytes([0x7D, 0x00]),
        FCSAlgorithm.CRC8: bytes([0x87, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x4B, 0x74]),
    },
    'ascii_BA': {
        FCSAlgorithm.CHECKSUM8: bytes([0x7D, 0x00]),
        FCSAlgorithm.CRC8: bytes([0xB1, 0x00]),
        FCSAlgorithm.CRC16: bytes([0x2E, 0x44]),
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