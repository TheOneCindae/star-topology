# Protocol Specification: Star-Topology Hub/Switch Demonstrator

This document specifies the wire protocol, frame format, FCS encoding conventions,
control message handling, and parser recovery rules for the application-layer
frame protocol used in this project.

## 1. Frame Format

```
┌────────┬──────┬──────┬──────┬──────┬──────┬──────────────────────┬──────────┐
│ START  │ DST  │ SRC  │ TYPE │ SEQ  │ LEN  │ PAYLOAD (0-64 bytes) │   FCS    │
│ (1 B)  │(1 B) │(1 B) │(1 B) │(1 B) │(1 B) │                      │  (2 B)   │
└────────┴──────┴──────┴──────┴──────┴──────┴──────────────────────┴──────────┘
```

### Field Definitions

| Field | Size | Value/Range | Description |
|-------|------|-------------|-------------|
| START | 1 byte | 0x7E (fixed) | Frame start marker |
| DST | 1 byte | 0x00-0x04, 0xFF | Destination node ID |
| SRC | 1 byte | 0x00-0x04 | Source node ID |
| TYPE | 1 byte | See Frame Types | Frame type |
| SEQ | 1 byte | 0x00-0x07 | Sequence number (low 3 bits) |
| LEN | 1 byte | 0-64 | Payload length in bytes |
| PAYLOAD | 0-64 bytes | - | Application data |
| FCS | 2 bytes | - | Frame Check Sequence |

**Total frame length:** 8 + LEN bytes (8 to 72 bytes)

### Node Identities

| ID | Role |
|----|------|
| 0x00 | Hub (server) |
| 0x01-0x04 | Client nodes 1-4 |
| 0xFF | Broadcast destination |

### Frame Types

| Type | Value | Direction | FCS Protected | Fault Injection |
|------|-------|-----------|---------------|-----------------|
| HELLO | 0x01 | Client→Hub | Yes | No (reliable) |
| CONFIG | 0x02 | Hub→Client | Yes | No (reliable) |
| DATA | 0x03 | Any→Any | Yes | Yes |
| ACK | 0x04 | Any→Any | Yes | No (reliable) |
| NACK | 0x05 | Any→Any | Yes | No (reliable) |
| JAM | 0x06 | Hub→Client | Yes | No (reliable) |
| CHAN | 0x07 | Hub→Client | Yes | No (reliable) |
| SLOT | 0x08 | Hub→Client | Yes | No (reliable) |
| STAT | 0x09 | Hub→Client | Yes | No (reliable) |

**Control messages (HELLO, CONFIG, ACK, NACK, JAM, CHAN, SLOT, STAT) are exempt from fault injection** to ensure reliable registration and experiment control.

---

## 2. FCS Wire Encoding

All three FCS algorithms compute their value over the **same protected fields**:
`DST || SRC || TYPE || SEQ || LEN || PAYLOAD` (6 + LEN bytes)

The START marker (0x7E) and the FCS field itself are **not** included in the protected data.

### 2.1 8-bit Checksum (CHECKSUM8)

**Algorithm:** Two's complement of the sum of all protected bytes modulo 256.

```
checksum = (-sum(protected_bytes)) & 0xFF
```

**Wire encoding:** Single byte (0x00-0xFF) placed in the first FCS byte. The second FCS byte is set to 0x00.

| Byte 0 | Byte 1 |
|--------|--------|
| checksum | 0x00 |

**Validation:** Receiver computes checksum over protected fields. Valid if computed == received_byte_0 AND received_byte_1 == 0x00.

### 2.2 CRC-8 (CRC8)

**Polynomial:** 0x07 (x⁸ + x² + x + 1) — reflected representation
**Initial value:** 0x00
**Input reflection:** Yes (bit-reflected per byte)
**Output reflection:** Yes
**Final XOR:** 0x00

**Processing convention:** Each input byte is processed LSB-first (reflected). The CRC register is shifted right. The polynomial 0x07 is used in its reflected form 0xE0 for the shift register, but the standard table-driven implementation with polynomial 0x07 and reflected input/output is used.

**Wire encoding:** Single byte placed in the first FCS byte. The second FCS byte is set to 0x00.

| Byte 0 | Byte 1 |
|--------|--------|
| crc8 | 0x00 |

**Test vector:** CRC-8 of ASCII `"123456789"` = 0xF4 (with above parameters)

### 2.3 CRC-16 (CRC16)

**Polynomial:** 0x1021 (x¹⁶ + x¹² + x⁵ + 1) — CCITT-FALSE
**Initial value:** 0x0000
**Input reflection:** No (normal bit order)
**Output reflection:** No
**Final XOR:** 0x0000

**Processing convention:** Each input byte is processed MSB-first. The CRC register is shifted left. Polynomial 0x1021 is applied when the MSB of the register is 1 before the shift.

**Wire encoding:** Two bytes, **big-endian** (network byte order).

| Byte 0 | Byte 1 |
|--------|--------|
| CRC high byte | CRC low byte |

**Test vector:** CRC-16-CCITT of ASCII `"123456789"` = 0x29B1

---

## 3. Sequence Number Arithmetic

Sequence numbers use **3 bits** (values 0-7). All comparisons and arithmetic must account for wraparound.

### Distance Function

```
distance(a, b) = (b - a) & 0x07  # forward distance from a to b (0-7)
```

### Comparison

- `a < b` in sequence space means `distance(a, b) <= 3` (half the modulus)
- This handles wraparound correctly for windows up to size 4

### Window Constraints

- Stop-and-Wait: window = 1
- Go-Back-N: max window = 7 (2³ - 1)
- Selective Repeat: max window = 4 (2³ / 2)

---

## 4. Control Message Handling

### 4.1 HELLO (Client → Hub)

**Payload:** Empty (LEN=0)
**Purpose:** Register client node ID
**Source validation:** Must match claimed node ID in registration
**Response:** CONFIG frame from hub

### 4.2 CONFIG (Hub → Client)

**Payload:** JSON-encoded experiment configuration
```json
{
  "node_id": 1,
  "forwarding_mode": "hub",
  "mac_protocol": "pure_aloha",
  "fcs_algorithm": "crc16",
  "arq_protocol": "stop_and_wait",
  "frame_duration_ms": 10.0,
  "slot_duration_ms": 10.0,
  "arq_timeout_ms": 100.0,
  "arq_window_size": 4,
  "arq_max_retries": 7
}
```
**Purpose:** Deliver experiment parameters to client

### 4.3 DATA (Any → Any)

**Payload:** Application data (0-64 bytes)
**Sequence number:** Used by ARQ protocols
**Fault injection:** Subject to configured loss/corruption

### 4.4 ACK (Any → Any)

**Payload:** Empty
**Sequence number:** Acknowledges the SEQ of the DATA frame
**Purpose:** Positive acknowledgement

### 4.5 NACK (Any → Any)

**Payload:** Empty
**Sequence number:** Requests retransmission of the SEQ
**Purpose:** Negative acknowledgement (Selective Repeat)

### 4.6 JAM (Hub → Client)

**Payload:** JSON `{"collided_nodes": [1, 2], "slot": 5}`
**Purpose:** Notify clients of detected collision

### 4.7 CHAN (Hub → Client)

**Payload:** JSON `{"state": "idle|busy", "reserved_by": 0}`
**Purpose:** Channel state notification for CSMA

### 4.8 SLOT (Hub → Client)

**Payload:** JSON `{"slot_number": 42, "duration_ms": 10.0}`
**Purpose:** Slot boundary notification for Slotted ALOHA

### 4.9 STAT (Hub → Client)

**Payload:** JSON statistics snapshot
**Purpose:** Periodic statistics broadcast

---

## 5. Parser Recovery Rules

The parser operates on a **persistent receive buffer** that accumulates TCP stream bytes.

### 5.1 Parsing Algorithm

1. **Append** new bytes to buffer
2. **Search** for START marker (0x7E) from current position
3. **If not found:** Discard all bytes before the last possible frame start (keep at most MAX_FRAME_SIZE - 1 bytes for partial frame)
4. **If found at position i:**
   - Discard bytes before i (garbage before start marker)
   - Check if at least MIN_FRAME_SIZE (8) bytes available from i
   - If not, wait for more data
   - Read LEN at offset i+5
   - Validate LEN ≤ MAX_PAYLOAD_LENGTH (64)
   - Check if full frame (8 + LEN bytes) available
   - If not, wait for more data
   - Extract frame, validate FCS
   - Advance buffer position past this frame
   - Repeat from step 2

### 5.2 Error Handling

| Error Condition | Action |
|-----------------|--------|
| Invalid START marker (not 0x7E) | Discard byte, continue search |
| LEN > 64 | Discard up to and including this START, continue |
| Frame truncated (connection closed) | Return partial frame error, clear buffer |
| FCS validation failure | Mark frame as corrupt, deliver to upper layer with error flag |
| Buffer exceeds max_frame_buffer | Clear buffer, log error, continue |

### 5.3 Buffer Management

- Maximum buffer size: 1 MB (configurable)
- On overflow: discard oldest bytes, keep most recent MAX_FRAME_SIZE bytes
- Garbage collection: after extracting N frames, compact buffer

---

## 6. TCP Framing Rules

- **Never assume** one `recv()` = one frame
- **Never assume** frame boundaries align with TCP segments
- The parser **must** handle:
  - Fragmented frames (header split across reads)
  - Coalesced frames (multiple frames in one read)
  - Mixed fragments and complete frames

---

## 7. Fault Injection Point

Fault injection is applied **after** FCS computation but **before** frame delivery to the MAC/forwarding layer.

```
[Frame Encode] → [Compute FCS] → [Fault Injector] → [Channel/MAC] → [Forward]
                    ↑                  ↑
              Protected          Corrupts PAYLOAD
              fields only        and/or FCS bytes
```

- **Frame loss:** Entire frame dropped (no delivery event)
- **Bit corruption:** Random bit flips in PAYLOAD and/or FCS bytes
- **Reproducibility:** Seeded RNG (configurable `fault_seed`)

---

## 8. ARQ Frame Sequencing

### DATA Frames
- Carry sequence number in SEQ field (low 3 bits)
- Retransmissions use **same sequence number** as original
- Original vs retransmission distinguished in statistics only

### ACK/NACK Frames
- Carry the sequence number being acknowledged
- Not counted as delivered application payload

---

## 9. Validation Requirements

### Server-Side Validation
1. HELLO: node_id in 1-4, not already registered, SRC matches registered connection
2. DATA: SRC matches registered connection for that socket, DST valid (0x00, 0x01-0x04, 0xFF)
3. All frames: LEN ≤ 64, valid TYPE, valid FCS (for FCS-protected types)

### Client-Side Validation
1. CONFIG: Valid JSON, contains expected fields
2. Received DATA: FCS valid, DST matches own node_id or 0xFF
3. ACK/NACK: SEQ matches outstanding transmission

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-10-12 | Initial specification |

---

*This specification must be finalized before implementing dependent modules (Phase 2+).*