# Star-Topology Hub/Switch Demonstrator

A modular Computer Networks demonstrator using a Raspberry Pi 5 as the central application-layer hub/switch with four Python client nodes.

## Project Overview

This project implements a custom frame protocol with hub/switch forwarding, three MAC protocols (Pure ALOHA, Slotted ALOHA, Non-persistent CSMA), three error detection methods (Checksum, CRC-8, CRC-16), controlled fault injection, and three ARQ protocols (Stop-and-Wait, Go-Back-N, Selective Repeat).

The networking carrier is real Wi-Fi/TCP. Collision behavior, fault injection, and experimental ARQ behavior are controlled at the application layer.

## Protocol Frame Format

```
START (1 byte) | DST (1 byte) | SRC (1 byte) | TYPE (1 byte) | SEQ (1 byte) | LEN (1 byte) | PAYLOAD (0-64 bytes) | FCS (2 bytes)
```

- START: 0x7E
- Hub ID: 0x00
- Client IDs: 0x01-0x04
- Broadcast DST: 0xFF
- Sequence numbers: low 3 bits (0-7)
- Total frame length: 8 + LEN bytes

## Frame Types

- HELLO (0x01): Client registration
- CONFIG (0x02): Server configuration
- DATA (0x03): Data payload
- ACK (0x04): Acknowledgement
- NACK (0x05): Negative acknowledgement
- JAM (0x06): Collision notification
- CHAN (0x07): Channel state
- SLOT (0x08): Slot boundary (Slotted ALOHA)
- STAT (0x09): Statistics

## Setup

```bash
cd star-topology
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the Hub and Dashboard

```bash
uvicorn server.main:create_app --factory --host 0.0.0.0 --port 8080
```

This single process runs the Raspberry Pi hub TCP service on port `5000` and
serves the dashboard/API on port `8080`. Open
`http://<raspberry-pi-ip>:8080/` from the node PC or another device.
The dashboard uses `/api` for status/events and `/ws/events` for live updates.

SQLite events are written to `data/star_topology.sqlite3`. Export recorded
events without inventing values:

```python
from storage.experiments import ExperimentStore
ExperimentStore().export_csv("data/events.csv")
```

## Running a Client

```bash
python -m client.main --id 1 --host 127.0.0.1 --port 5000
```

The server must be started first. Run each additional client in a separate
terminal with a unique ID from 1 through 4. Each client sends a FCS-protected
HELLO frame and remains connected after receiving its CONFIG response. Stop a
process with `Ctrl+C`.

To request a transfer to another connected node:

```bash
python -m client.main --id 1 --host 192.168.1.50 --port 5000 --send-to 2 --message "hello from node 1"
```

The Raspberry Pi approves the request only when the destination is connected,
then forwards the DATA frame. Requests for disconnected destinations are denied
and appear in the dashboard activity log.

## Running Tests

```bash
pytest -q
```

## Project Structure

```
star-topology/
├── server/          # TCP server, registry, forwarding, channel, fault injection
├── client/          # Client node implementation
├── protocols/       # Frame encoding, parsing, FCS, MAC, ARQ protocols
├── api/             # FastAPI routes and WebSocket handlers
├── dashboard/       # HTML/CSS/JS dashboard
├── storage/         # SQLite database and CSV export
├── tests/           # Unit and integration tests
└── data/            # Runtime data (databases, exports)
```

## Current Milestone Status

- [x] Milestone 1: Repository, configuration model, test framework
- [x] Milestone 2: Frame encoding, decoding, parsing, unit tests
- [x] Milestone 3: Asyncio TCP server, client registration, connection registry
- [x] Milestone 4: Hub forwarding, switch learning, flooding, entry aging
- [x] Milestone 5: Channel timing, three MAC protocols
- [x] Milestone 6: Checksum, CRC-8, CRC-16, controlled DATA-only fault injection
- [x] Milestone 7: Stop-and-Wait, Go-Back-N, Selective Repeat
- [x] Milestone 8: Shared statistics, SQLite logging, CSV export
- [x] Milestone 9: FastAPI controls, WebSocket events, dashboard
- [x] Milestone 10: Integration, deployment, experiments, documentation

## Limitations

ARQ modules are deterministic application-layer simulations: callers provide an
async transmit/acknowledgement callback. They do not replace TCP reliability.
Fault injection only operates on encoded DATA frames and deliberately leaves
control frames untouched. The dashboard reports stored/live events; it does not
fabricate throughput, latency, or loss metrics.

## License

Educational project for Computer Networks laboratory.