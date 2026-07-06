from datetime import datetime

import pytest

from broadlink6.device import Device
from broadlink6.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BroadlinkError,
    raise_for_error_code,
)
from broadlink6.protocol import (
    checksum,
    data_to_pulses,
    pack_command,
    pack_hello,
    parse_hello,
    pulses_to_data,
    response_error_code,
    validate_response,
)

RM4_MAC = bytes.fromhex("348e892e2334")


def test_checksum_seed_and_accumulation():
    assert checksum(b"") == 0xBEAF
    assert checksum(b"\x01\x02") == 0xBEB2


def test_pack_hello_layout():
    when = datetime(2026, 7, 5, 18, 40)
    packet = pack_hello(source_port=54321, when=when, utc_offset=-4)

    assert len(packet) == 0x30
    assert packet[0x26] == 0x06
    assert packet[0x0C:0x0E] == (2026).to_bytes(2, "little")
    assert packet[0x13] == 7
    assert packet[0x12] == 5
    assert packet[0x18:0x1C] == bytes(4)
    assert packet[0x1C:0x1E] == (54321).to_bytes(2, "little")

    unstamped = bytearray(packet)
    unstamped[0x20:0x22] = b"\x00\x00"
    assert packet[0x20:0x22] == checksum(unstamped).to_bytes(2, "little")


def test_parse_hello_reads_identity():
    response = bytearray(0x80)
    response[0x34:0x36] = (0x520B).to_bytes(2, "little")
    response[0x3A:0x40] = RM4_MAC[::-1]
    response[0x40:0x40 + 12] = "智能遥控".encode()

    info = parse_hello(bytes(response))

    assert info.devtype == 0x520B
    assert info.mac == RM4_MAC
    assert info.name == "智能遥控"
    assert info.is_locked is False


def test_pulses_to_data_single_byte_ticks():
    assert pulses_to_data([550]) == bytes((0x26, 0x00, 0x01, 0x00, 0x10))


def test_pulses_to_data_multi_byte_ticks():
    assert pulses_to_data([65000]) == bytes((0x26, 0x00, 0x03, 0x00, 0x00, 0x07, 0xBB))


def test_pulses_survive_round_trip_within_tick_error():
    pulses = [4350, 4350, 550, 1550, 550, 550, 65000]
    recovered = data_to_pulses(pulses_to_data(pulses))

    assert len(recovered) == len(pulses)
    for original, result in zip(pulses, recovered):
        assert abs(original - result) < 33


def test_pack_command_layout_and_validation():
    packet = pack_command(
        packet_type=0x6A,
        devtype=0x520B,
        mac=RM4_MAC,
        device_id=0x11223344,
        count=0x8001,
        payload_checksum=0xBEAF,
        encrypted_payload=bytes(16),
    )

    assert packet[0x00:0x08] == bytes.fromhex("5aa5aa555aa5aa55")
    assert packet[0x24:0x26] == (0x520B).to_bytes(2, "little")
    assert packet[0x26:0x28] == (0x6A).to_bytes(2, "little")
    assert packet[0x2A:0x30] == RM4_MAC[::-1]
    assert packet[0x30:0x34] == (0x11223344).to_bytes(4, "little")

    validate_response(packet)
    assert response_error_code(packet) == 0


def test_validate_response_rejects_corruption():
    packet = pack_command(0x6A, 0x520B, RM4_MAC, 0, 0x8001, 0, bytes(16))
    corrupted = bytearray(packet)
    corrupted[0x30] ^= 0xFF

    with pytest.raises(ValueError):
        validate_response(bytes(corrupted))


def test_error_code_mapping():
    raise_for_error_code(0)

    with pytest.raises(AuthenticationError):
        raise_for_error_code(-1)
    with pytest.raises(AuthorizationError):
        raise_for_error_code(-7)
    with pytest.raises(BroadlinkError):
        raise_for_error_code(-999)


def test_device_encryption_round_trip():
    device = Device("::1", 0x520B, "34:8e:89:2e:23:34")

    assert device.mac == RM4_MAC

    payload = bytes(range(32))
    assert device._decrypt(device._encrypt(payload)) == payload
