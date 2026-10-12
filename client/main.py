"""Command-line entry point for a registering client node."""

import argparse
import asyncio

from client.node_client import NodeClient


async def run(node_id: int, host: str, port: int) -> None:
    client = NodeClient(node_id=node_id, host=host, port=port)
    config = await client.connect()
    print(f"Node {node_id} registered: {config}")
    try:
        await asyncio.Event().wait()
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Star-Topology client node")
    parser.add_argument("--id", type=int, required=True, dest="node_id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.node_id, args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
