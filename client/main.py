"""Command-line entry point for a registering client node."""

import argparse
import asyncio

from client.node_client import NodeClient
from server.config import FrameType


async def run(node_id: int, host: str, port: int, destination: int | None, message: str) -> None:
    client = NodeClient(node_id=node_id, host=host, port=port)
    config = await client.connect()
    print(f"Node {node_id} registered: {config}")
    if destination is not None:
        await client.send_data(destination, message.encode("utf-8"))
        print(f"Transfer requested: node {node_id} -> node {destination}")
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
    args = parser.parse_args()
    try:
        asyncio.run(run(args.node_id, args.host, args.port, args.send_to, args.message))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
