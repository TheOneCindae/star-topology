"""Command-line entry point for a registering client node."""

import argparse
import asyncio

from client.node_client import NodeClient
from server.config import FrameType


async def run(
    node_id: int, host: str, port: int, destination: int | None, message: str,
    traffic_interval_ms: float | None = None, traffic_count: int | None = None,
    credential: str | None = None,
) -> None:
    client = NodeClient(node_id=node_id, host=host, port=port, credential=credential)
    config = await client.connect()
    print(f"Node {node_id} registered: {config}")
    if destination is not None:
        if traffic_interval_ms is None:
            result = await client.send_data(destination, message.encode("utf-8"))
            print(
                f"Transfer requested: node {node_id} -> node {destination} "
                f"(success={result.success}, attempts={result.attempts})"
            )
        else:
            results = await client.generate_traffic(
                destination, traffic_interval_ms, traffic_count
            )
            print(f"Generated {len(results)} traffic frames")
    try:
        while True:
            frame = await client.receive_frame()
            if frame.type == FrameType.DATA:
                print(
                    f"Node {node_id} received from Node {frame.src}: "
                    f"{frame.payload.decode('utf-8', errors='replace')}"
                )
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Star-Topology client node")
    parser.add_argument("--id", type=int, required=True, dest="node_id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--send-to", type=int, choices=range(1, 5))
    parser.add_argument("--message", default="")
    parser.add_argument("--traffic-interval-ms", type=float)
    parser.add_argument("--traffic-count", type=int)
    parser.add_argument("--credential")
    args = parser.parse_args()
    try:
        asyncio.run(run(
            args.node_id, args.host, args.port, args.send_to, args.message,
            args.traffic_interval_ms, args.traffic_count, args.credential,
        ))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
