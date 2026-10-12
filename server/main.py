"""Command-line entry point for the registration server."""

import asyncio
import argparse

from server.tcp_server import TCPServer


def create_app() :
    """Create the HTTP application; useful for uvicorn and embedding."""
    return TCPServer().app


async def run(host: str, port: int) -> None:
    server = TCPServer(host=host, port=port)
    await server.start()
    print(f"TCP server listening on {server.address[0]}:{server.address[1]}")
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Star-Topology TCP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
