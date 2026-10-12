import asyncio

import pytest

from protocols.frame import create_data_frame, encode_frame
from protocols.fcs import compute_fcs
from protocols.go_back_n import GoBackN
from protocols.selective_repeat import SelectiveRepeat
from protocols.stop_and_wait import StopAndWait
from server.fault_injector import FaultInjector
from storage.database import Database
from storage.experiments import export_csv


def encoded(frame):
    protected = bytes((frame.dst, frame.src, frame.type, frame.seq, frame.len)) + frame.payload
    return encode_frame(frame, compute_fcs("crc16", protected))


def test_faults_are_reproducible_and_control_safe(tmp_path):
    data = encoded(create_data_frame(2, 1, 0, b"payload"))
    one = FaultInjector(bit_error_rate=0.2, seed=3).inject(data)
    two = FaultInjector(bit_error_rate=0.2, seed=3).inject(data)
    assert one == two
    control = bytes([0x7E, 2, 0, 2, 0, 0, 0, 0])
    assert FaultInjector(loss_probability=1, bit_error_rate=1, seed=1).inject(control).data == control


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", [StopAndWait, GoBackN, SelectiveRepeat])
async def test_arq_retries_and_sequence_wrap(protocol):
    kwargs = {"start_sequence": 7, "max_retries": 1}
    if protocol is GoBackN:
        kwargs["window_size"] = 2
    if protocol is SelectiveRepeat:
        kwargs["window_size"] = 2
    calls = []

    async def transmit(packet, sequence, attempt):
        calls.append((packet, sequence, attempt))
        return attempt > 0

    result = await protocol(**kwargs).send(["a"], transmit)
    assert result.success and result.retransmissions == 1
    assert calls[0][1] == 7


def test_database_and_csv_export(tmp_path):
    db = Database(":memory:")
    db.record_event("frame", {"seq": 1})
    assert db.stats() == {"frame": 1}
    destination = export_csv(db, tmp_path / "events.csv")
    assert "frame" in destination.read_text(encoding="utf-8")
    db.close()
