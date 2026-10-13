# Star-Topology Hub/Switch Demonstrator

A modular Computer Networks demonstrator using a Raspberry Pi 5 as the central application-layer hub/switch with four Python client nodes.

## Project Overview

This project implements a custom frame protocol with hub/switch forwarding, three MAC protocols (Pure ALOHA, Slotted ALOHA, Non-persistent CSMA), three error detection methods (Checksum, CRC-8, CRC-16), controlled fault injection, and three ARQ protocol simulations (Stop-and-Wait, Go-Back-N, Selective Repeat).

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

Set an administrator token before starting the service:

```bash
export STAR_TOPOLOGY_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export STAR_TOPOLOGY_AUTH_REQUIRED=1
```

Provision each node once through the dashboard/API, then pass its returned
credential to the node with `--credential`. Credentials are stored as salted
hashes. Keep the admin token private.

SQLite events are written to `data/star_topology.sqlite3`. Export recorded
events without inventing values:

```python
from storage.experiments import ExperimentStore
ExperimentStore().export_csv("data/events.csv")
```

For repeatable local validation, run the complete MAC × FCS × ARQ matrix:

```bash
python scripts/run_experiments.py --output experiment-exports
```

This creates one CSV per combination from events recorded by the live server
and client path. On the lab setup, run the same traffic commands with the Pi
and four physical PCs, then export the Pi database after each experiment.

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

For generated traffic, use a bounded count or omit the count for continuous
traffic:

```bash
python -m client.main --id 1 --host 192.168.1.50 --send-to 2 \
  --traffic-interval-ms 100 --traffic-count 20
```

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
- [x] Milestone 5: Channel timing and live MAC integration
- [x] Milestone 6: Checksum, CRC-8, CRC-16
- [x] Milestone 7: Stop-and-Wait, Go-Back-N, Selective Repeat simulations
- [x] Milestone 8: Live fault injection, shared statistics, SQLite logging, CSV export
- [x] Milestone 9: FastAPI controls, WebSocket events, dashboard
- [ ] Milestone 10: Physical Pi/four-PC acceptance and network-isolation proof

## Limitations

ARQ modules are deterministic application-layer simulations: callers provide an
async transmit/acknowledgement callback. They do not replace TCP reliability.
Fault injection only operates on encoded DATA frames and deliberately leaves
control frames untouched. The dashboard reports stored/live events; it does not
fabricate throughput, latency, or loss metrics.

The project requires Python 3.10 or newer. Live DATA forwarding now passes
through the configured MAC decision, channel timing, fault injector, and
acknowledgement-based ARQ client. The ARQ algorithms remain application-layer
reliability on top of the TCP control connection.
Authentication, node revocation, persistent ACLs, audit logs, and authenticated
administration are implemented. Network-level peer isolation still has to be
configured and demonstrated on the Raspberry Pi; the application cannot enforce
Wi-Fi client isolation by itself.

## Raspberry Pi and lab deployment

Run the hub and dashboard on the Raspberry Pi, and run one node client on each
of the four PCs. Put all devices on the same router, or enable a Pi hotspot.
Give the Pi a stable LAN address and use that address for every node's
`--host` value. Allow TCP port 5000 for node connections and HTTP port 8080
for the dashboard.

On the Pi:

```bash
uvicorn server.main:create_app --factory --host 0.0.0.0 --port 8080
```

Open `http://<pi-ip>:8080/` from a PC browser. On each node PC:

```bash
python -m client.main --id 1 --host <pi-ip> --port 5000
```

Use a different ID from 1 through 4 on each PC. A node can send an approved
transfer with `--send-to 2 --credential <node-credential> --message "hello"`.

The repository also includes `scripts/run-hub.sh`, `scripts/run-node.sh`,
`scripts/run-hub.ps1`, and `scripts/run-node.ps1`. For a Pi service install,
copy `deploy/star-topology.service` to `/etc/systemd/system`, create the
`star-topology` service user and `/var/lib/star-topology`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now star-topology
```

## License

Educational project for Computer Networks laboratory.