"""
Configuration model for the Star-Topology Hub/Switch demonstrator.

This module defines all configurable parameters for the server, experiments,
and protocol behavior. It provides a single source of truth for configuration
with validation and sensible defaults.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional
import json


# Node identity constants
HUB_ID = 0x00
CLIENT_ID_MIN = 0x01
CLIENT_ID_MAX = 0x04
BROADCAST_ID = 0xFF

# Frame constants
START_MARKER = 0x7E
MAX_PAYLOAD_LENGTH = 64
FRAME_HEADER_SIZE = 6  # START, DST, SRC, TYPE, SEQ, LEN
FCS_SIZE = 2
MIN_FRAME_SIZE = FRAME_HEADER_SIZE + FCS_SIZE  # 8 bytes (empty payload)
MAX_FRAME_SIZE = FRAME_HEADER_SIZE + MAX_PAYLOAD_LENGTH + FCS_SIZE  # 72 bytes

# Frame type constants
class FrameType:
    HELLO = 0x01
    CONFIG = 0x02
    DATA = 0x03
    ACK = 0x04
    NACK = 0x05
    JAM = 0x06
    CHAN = 0x07
    SLOT = 0x08
    STAT = 0x09

    @classmethod
    def is_valid(cls, value: int) -> bool:
        return value in (cls.HELLO, cls.CONFIG, cls.DATA, cls.ACK,
                         cls.NACK, cls.JAM, cls.CHAN, cls.SLOT, cls.STAT)

    @classmethod
    def name(cls, value: int) -> str:
        names = {
            cls.HELLO: "HELLO",
            cls.CONFIG: "CONFIG",
            cls.DATA: "DATA",
            cls.ACK: "ACK",
            cls.NACK: "NACK",
            cls.JAM: "JAM",
            cls.CHAN: "CHAN",
            cls.SLOT: "SLOT",
            cls.STAT: "STAT",
        }
        return names.get(value, f"UNKNOWN(0x{value:02X})")


# FCS algorithm constants
class FCSAlgorithm:
    CHECKSUM8 = "checksum8"
    CRC8 = "crc8"
    CRC16 = "crc16"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in (cls.CHECKSUM8, cls.CRC8, cls.CRC16)


# MAC protocol constants
class MACProtocol:
    PURE_ALOHA = "pure_aloha"
    SLOTTED_ALOHA = "slotted_aloha"
    CSMA_NON_PERSISTENT = "csma_non_persistent"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in (cls.PURE_ALOHA, cls.SLOTTED_ALOHA, cls.CSMA_NON_PERSISTENT)


# ARQ protocol constants
class ARQProtocol:
    STOP_AND_WAIT = "stop_and_wait"
    GO_BACK_N = "go_back_n"
    SELECTIVE_REPEAT = "selective_repeat"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in (cls.STOP_AND_WAIT, cls.GO_BACK_N, cls.SELECTIVE_REPEAT)


# Forwarding mode constants
class ForwardingMode:
    HUB = "hub"
    SWITCH = "switch"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in (cls.HUB, cls.SWITCH)


@dataclass
class ServerConfig:
    """Main server configuration."""
    host: str = "0.0.0.0"
    tcp_port: int = 5000
    http_port: int = 8080
    max_clients: int = 4
    client_timeout: float = 30.0  # seconds
    buffer_size: int = 4096
    max_frame_buffer: int = 1024 * 1024  # 1 MB max buffer for parser


@dataclass
class ExperimentConfig:
    """Experiment configuration parameters."""
    # Forwarding
    forwarding_mode: str = ForwardingMode.HUB

    # MAC layer
    mac_protocol: str = MACProtocol.PURE_ALOHA
    frame_duration_ms: float = 10.0  # Tf - frame transmission time
    slot_duration_ms: float = 10.0   # Slot duration for Slotted ALOHA
    backoff_min_ms: float = 5.0      # Minimum backoff for CSMA
    backoff_max_ms: float = 50.0     # Maximum backoff for CSMA

    # FCS/Error detection
    fcs_algorithm: str = FCSAlgorithm.CRC16

    # ARQ layer
    arq_protocol: str = ARQProtocol.STOP_AND_WAIT
    arq_window_size: int = 4         # For Go-Back-N and Selective Repeat
    arq_timeout_ms: float = 100.0    # ACK timeout
    arq_max_retries: int = 7         # Maximum retransmission attempts

    # Fault injection
    frame_loss_probability: float = 0.0    # 0.0 to 1.0
    bit_error_rate: float = 0.0            # Bit error rate (per bit)
    fault_seed: Optional[int] = None       # Random seed for reproducibility

    # Experiment control
    experiment_duration_sec: Optional[float] = None  # None = run indefinitely
    traffic_interval_ms: float = 100.0  # Inter-packet generation interval

    def __post_init__(self):
        """Validate configuration values."""
        if not ForwardingMode.is_valid(self.forwarding_mode):
            raise ValueError(f"Invalid forwarding_mode: {self.forwarding_mode}")
        if not MACProtocol.is_valid(self.mac_protocol):
            raise ValueError(f"Invalid mac_protocol: {self.mac_protocol}")
        if not FCSAlgorithm.is_valid(self.fcs_algorithm):
            raise ValueError(f"Invalid fcs_algorithm: {self.fcs_algorithm}")
        if not ARQProtocol.is_valid(self.arq_protocol):
            raise ValueError(f"Invalid arq_protocol: {self.arq_protocol}")

        if not (0 <= self.frame_loss_probability <= 1):
            raise ValueError("frame_loss_probability must be in [0, 1]")
        if not (0 <= self.bit_error_rate <= 1):
            raise ValueError("bit_error_rate must be in [0, 1]")
        if self.arq_window_size < 1 or self.arq_window_size > 7:
            raise ValueError("arq_window_size must be in [1, 7] (3-bit sequence numbers)")
        if self.arq_max_retries < 0:
            raise ValueError("arq_max_retries must be >= 0")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "forwarding_mode": self.forwarding_mode,
            "mac_protocol": self.mac_protocol,
            "frame_duration_ms": self.frame_duration_ms,
            "slot_duration_ms": self.slot_duration_ms,
            "backoff_min_ms": self.backoff_min_ms,
            "backoff_max_ms": self.backoff_max_ms,
            "fcs_algorithm": self.fcs_algorithm,
            "arq_protocol": self.arq_protocol,
            "arq_window_size": self.arq_window_size,
            "arq_timeout_ms": self.arq_timeout_ms,
            "arq_max_retries": self.arq_max_retries,
            "frame_loss_probability": self.frame_loss_probability,
            "bit_error_rate": self.bit_error_rate,
            "fault_seed": self.fault_seed,
            "experiment_duration_sec": self.experiment_duration_sec,
            "traffic_interval_ms": self.traffic_interval_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentConfig":
        """Create from dictionary."""
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ExperimentConfig":
        """Deserialize from JSON."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ClientConfig:
    """Client node configuration."""
    node_id: int
    server_host: str = "127.0.0.1"
    server_port: int = 5000
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10

    def __post_init__(self):
        if not (CLIENT_ID_MIN <= self.node_id <= CLIENT_ID_MAX):
            raise ValueError(f"node_id must be in [{CLIENT_ID_MIN}, {CLIENT_ID_MAX}]")


# Default configurations
DEFAULT_SERVER_CONFIG = ServerConfig()
DEFAULT_EXPERIMENT_CONFIG = ExperimentConfig()