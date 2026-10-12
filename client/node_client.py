"""Asyncio client helper for registering a node with the TCP server."""

import asyncio
import json
from typing import Optional

from protocols.fcs import compute_fcs, validate_fcs
from protocols.frame import create_hello_frame, decode_frame, encode_frame
from protocols.parser import FrameParser
from server.config import ExperimentConfig, FrameType


class NodeClient:
    """Client that connects and completes the HELLO/CONFIG handshake."""

    def __init__(
        self,
        node_id: int,
        host: str = "127.0.0.1",
        port: int = 5000,
        fcs_algorithm: str = ExperimentConfig().fcs_algorithm,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.fcs_algorithm = fcs_algorithm
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

    async def connect(self) -> dict:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        frame = create_hello_frame(self.node_id)
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        fcs = compute_fcs(self.fcs_algorithm, protected)
        self.writer.write(encode_frame(frame, fcs))
        await self.writer.drain()

        parser = FrameParser(
            validate_fcs_fn=lambda received, data: validate_fcs(
                self.fcs_algorithm, received, data
            )
        )
        while True:
            data = await self.reader.read(4096)
            if not data:
                raise ConnectionError("Server closed before sending CONFIG")
            result = parser.feed(data)
            for response in result.frames:
                if not response.valid_fcs:
                    raise ValueError("CONFIG frame has invalid FCS")
                if response.type != FrameType.CONFIG:
                    continue
                return json.loads(response.payload.decode("ascii"))

    async def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
