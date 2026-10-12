"""
Protocols package for Star-Topology Hub/Switch demonstrator.

Contains frame encoding/decoding, parsing, FCS algorithms,
MAC protocols, and ARQ implementations.
"""

from .frame import Frame, encode_frame, decode_frame
from .parser import FrameParser, create_parser
from .fcs import (
    compute_fcs, validate_fcs, get_fcs_name,
    FCSAlgorithm, FCSAlgorithmRegistry
)

__all__ = [
    "Frame",
    "encode_frame",
    "decode_frame",
    "FrameParser",
    "create_parser",
    "compute_fcs",
    "validate_fcs",
    "get_fcs_name",
    "FCSAlgorithm",
    "FCSAlgorithmRegistry",
]