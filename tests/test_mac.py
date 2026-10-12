import random

import pytest

from protocols.mac import (
    MACDecision,
    NonPersistentCSMA,
    PureALOHA,
    SlottedALOHA,
    create_mac_protocol,
)
from server.channel import Channel
from server.config import MACProtocol


def test_channel_tracks_busy_state_and_expiry():
    now = [0.0]
    channel = Channel(frame_duration=1.0, clock=lambda: now[0])

    channel.begin(1)
    assert channel.busy is True
    now[0] = 1.0
    assert channel.busy is False


def test_channel_counts_overlapping_transmissions_as_collision():
    channel = Channel(frame_duration=1.0, clock=lambda: 0.0)

    channel.begin(1)
    channel.begin(2)

    assert channel.collision_count == 1
    assert len(channel.active_transmissions) == 2


def test_pure_aloha_transmits_even_when_channel_is_busy():
    mac = PureALOHA()

    assert mac.decide(True) is MACDecision.TRANSMIT
    assert mac.stats.attempts == 1
    assert mac.stats.transmissions == 1


def test_slotted_aloha_waits_until_slot_boundary():
    mac = SlottedALOHA()

    assert mac.decide(False, slot_boundary=False) is MACDecision.WAIT_FOR_SLOT
    assert mac.decide(False, slot_boundary=True) is MACDecision.TRANSMIT
    assert mac.stats.deferrals == 1


def test_nonpersistent_csma_backoff_is_reproducible():
    mac = NonPersistentCSMA(1.0, 2.0, random.Random(7))

    assert mac.decide(True) is MACDecision.DEFER
    assert mac.last_backoff == pytest.approx(1.3238327648)
    assert mac.decide(False) is MACDecision.TRANSMIT
    assert mac.last_backoff is None


@pytest.mark.parametrize(
    "protocol, expected_type",
    [
        (MACProtocol.PURE_ALOHA, PureALOHA),
        (MACProtocol.SLOTTED_ALOHA, SlottedALOHA),
        (MACProtocol.CSMA_NON_PERSISTENT, NonPersistentCSMA),
    ],
)
def test_mac_factory(protocol, expected_type):
    assert isinstance(create_mac_protocol(protocol), expected_type)
