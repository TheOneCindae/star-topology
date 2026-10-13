"""Asyncio client helper for registering a node with the TCP server."""

import asyncio
import json
from typing import Optional

from protocols.fcs import compute_fcs, validate_fcs
from protocols.frame import Frame, create_data_frame, create_hello_frame, encode_frame
from protocols.parser import FrameParser
from protocols._arq import ARQResult
from protocols.go_back_n import GoBackN
from protocols.selective_repeat import SelectiveRepeat
from protocols.stop_and_wait import StopAndWait
from server.config import ExperimentConfig, FCSAlgorithm, FrameType


class NodeClient:
    """Client that connects and completes the HELLO/CONFIG handshake."""

    def __init__(
        self,
        node_id: int,
        host: str = "127.0.0.1",
        port: int = 5000,
        fcs_algorithm: str = ExperimentConfig().fcs_algorithm,
        credential: str | None = None,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.fcs_algorithm = fcs_algorithm
        self.credential = credential
        self.config: dict = {}
        self._received: asyncio.Queue[Frame] = asyncio.Queue()
        self._receiver_task: Optional[asyncio.Task[None]] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._parser = FrameParser(
            validate_fcs_fn=lambda received, data: validate_fcs(
                self.fcs_algorithm, received, data
            )
        )

    async def connect(self) -> dict:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        frame = create_hello_frame(self.node_id, self.credential)
        protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
        protected += frame.payload
        fcs = compute_fcs(self.fcs_algorithm, protected)
        self.writer.write(encode_frame(frame, fcs))
        await self.writer.drain()

        while True:
            try:
                data = await asyncio.wait_for(self.reader.read(4096), timeout=5.0)
            except asyncio.TimeoutError as exc:
                raise ConnectionError("Timed out waiting for server handshake") from exc
            if not data:
                raise ConnectionError("Server closed before sending CONFIG")
            result = self._parser.feed(data)
            for response in result.frames:
                if not response.valid_fcs:
                    raise ValueError("CONFIG frame has invalid FCS")
                if response.type == FrameType.NACK:
                    raise ConnectionError("Server rejected node authentication")
                if response.type != FrameType.CONFIG:
                    continue
                raw_config = json.loads(response.payload.decode("ascii"))
                self.config = raw_config
                self.fcs_algorithm = {
                    0: FCSAlgorithm.CHECKSUM8,
                    1: FCSAlgorithm.CRC8,
                    2: FCSAlgorithm.CRC16,
                }.get(raw_config.get("f"), self.fcs_algorithm)
                self._receiver_task = asyncio.create_task(self._receive_loop())
                return {"node_id": raw_config["n"]}

    async def _receive_loop(self) -> None:
        try:
            while True:
                data = await self.reader.read(4096) if self.reader else b""
                if not data:
                    raise ConnectionError("Server closed the node connection")
                result = self._parser.feed(data)
                for frame in result.frames:
                    if not frame.valid_fcs:
                        continue
                    await self._received.put(frame)
        except (ConnectionError, asyncio.CancelledError):
            return

    async def receive_frame(self) -> "Frame":
        """Receive the next validated frame sent by the hub."""
        if self.reader is None:
            raise ConnectionError("Node is not connected")
        return await self._received.get()

    async def close(self) -> None:
        if self.writer is not None:
            if self._receiver_task is not None:
                self._receiver_task.cancel()
                await asyncio.gather(self._receiver_task, return_exceptions=True)
                self._receiver_task = None
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None

    async def send_data(
        self, destination: int, payload: bytes, seq: int = 0
    ) -> ARQResult:
        """Ask the hub to approve and forward DATA to a chosen node."""
        if self.writer is None:
            raise ConnectionError("Node is not connected")
        writer = self.writer
        timeout = float(self.config.get("t", 100)) / 1000
        retries = int(self.config.get("r", 2))

        async def transmit(_packet: bytes, sequence: int, attempt: int) -> bool:
            frame = create_data_frame(destination, self.node_id, sequence, payload)
            protected = bytes([frame.dst, frame.src, frame.type, frame.seq, frame.len])
            protected += frame.payload
            writer.write(encode_frame(frame, compute_fcs(self.fcs_algorithm, protected)))
            await writer.drain()
            try:
                while True:
                    response = await self.receive_frame()
                    if response.type == FrameType.ACK and response.seq == sequence:
                        return True
                    if response.type == FrameType.NACK and response.seq == sequence:
                        return False
            except ConnectionError:
                return False

        arq_type = self.config.get("a", 0)
        arq_class = {
            0: StopAndWait,
            1: GoBackN,
            2: SelectiveRepeat,
        }.get(arq_type, StopAndWait)
        if arq_class is StopAndWait:
            arq = arq_class(timeout=timeout, max_retries=retries, start_sequence=seq)
        else:
            arq = arq_class(
                window_size=min(4, int(self.config.get("w", 4))),
                timeout=timeout,
                max_retries=retries,
                start_sequence=seq,
            )
        result = await arq.send([payload], transmit)
        return result

    async def generate_traffic(
        self, destination: int, interval_ms: float, count: int | None = None
    ) -> list[ARQResult]:
        """Generate bounded or continuous DATA traffic at the configured interval."""
        results: list[ARQResult] = []
        index = 0
        while count is None or index < count:
            results.append(
                await self.send_data(destination, f"traffic-{index}".encode(), index & 7)
            )
            index += 1
            if count is None or index < count:
                await asyncio.sleep(interval_ms / 1000)
        return results
