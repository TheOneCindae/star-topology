"""Command-line entry point for the registration server."""

import asyncio
import argparse
import os

from server.tcp_server import TCPServer


def create_app():
    """Create the dashboard/API app and its Raspberry Pi TCP hub."""
    host = os.getenv("STAR_TOPOLOGY_TCP_HOST", "0.0.0.0")
    port = int(os.getenv("STAR_TOPOLOGY_TCP_PORT", "5000"))
    database_path = os.getenv("STAR_TOPOLOGY_DB_PATH", "data/star_topology.sqlite3")
    auth_required = os.getenv("STAR_TOPOLOGY_AUTH_REQUIRED", "1") == "1"
    return TCPServer(
        host=host,
        port=port,
        database_path=database_path,
        authentication_required=auth_required,
    ).app


async def run(host: str, port: int) -> None:
    database_path = os.getenv("STAR_TOPOLOGY_DB_PATH", "data/star_topology.sqlite3")
    auth_required = os.getenv("STAR_TOPOLOGY_AUTH_REQUIRED", "1") == "1"
    server = TCPServer(
        host=host,
        port=port,
        database_path=database_path,
        authentication_required=auth_required,
    )
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
