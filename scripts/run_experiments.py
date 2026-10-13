"""Run the local MAC x FCS x ARQ matrix and export recorded events."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from client.node_client import NodeClient
from server.config import (
    ARQProtocol,
    ExperimentConfig,
    FCSAlgorithm,
    MACProtocol,
)
from server.tcp_server import TCPServer
from storage.experiments import export_csv


async def run_matrix(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for mac in (
        MACProtocol.PURE_ALOHA,
        MACProtocol.SLOTTED_ALOHA,
        MACProtocol.CSMA_NON_PERSISTENT,
    ):
        for fcs in (FCSAlgorithm.CHECKSUM8, FCSAlgorithm.CRC8, FCSAlgorithm.CRC16):
            for arq in (
                ARQProtocol.STOP_AND_WAIT,
                ARQProtocol.GO_BACK_N,
                ARQProtocol.SELECTIVE_REPEAT,
            ):
                config = ExperimentConfig(
                    mac_protocol=mac,
                    fcs_algorithm=fcs,
                    arq_protocol=arq,
                    arq_timeout_ms=200,
                    arq_max_retries=2,
                )
                server = TCPServer(experiment_config=config)
                await server.start()
                sender = NodeClient(1, *server.address, fcs_algorithm=fcs)
                receiver = NodeClient(2, *server.address, fcs_algorithm=fcs)
                try:
                    await sender.connect()
                    await receiver.connect()
                    await sender.generate_traffic(2, 1, count=3)
                    name = f"{mac}_{fcs}_{arq}.csv"
                    export_csv(server.database, output_dir / name)
                finally:
                    await sender.close()
                    await receiver.close()
                    await server.stop()
                print(f"exported {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("experiment-exports"))
    args = parser.parse_args()
    asyncio.run(run_matrix(args.output))


if __name__ == "__main__":
    main()
