"""Broadlink wire protocol primitives: packet layouts, checksums, IR encoding."""

from dataclasses import dataclass
from datetime import datetime

DEFAULT_PORT = 80

# Duration unit of the IR packet format, in microseconds (2^-15 s).
IR_TICK = 32.84

COMMAND_HELLO = 0x06
COMMAND_AUTH = 0x65
COMMAND_CONTROL = 0x6A


@dataclass(frozen=True)
class DeviceInfo:
    """Identity a device reports in its hello response."""

    devtype: int
    mac: bytes
    name: str
    is_locked: bool


def checksum(data: bytes) -> int:
    """Compute the checksum used across all Broadlink packets."""
    return sum(data, 0xBEAF) & 0xFFFF


def pack_hello(source_port: int, when: datetime | None = None, utc_offset: int = 0) -> bytes:
    """Build a hello packet.

    The local-address field (0x18:0x1C) is left zeroed: an IPv6-only client
    has no IPv4 address to advertise, and devices answer to the UDP source
    regardless.
    """
    when = when or datetime.now()
    packet = bytearray(0x30)

    packet[0x08:0x0C] = utc_offset.to_bytes(4, "little", signed=True)
    packet[0x0C:0x0E] = when.year.to_bytes(2, "little")
    packet[0x0E] = when.minute
    packet[0x0F] = when.hour
    packet[0x10] = when.year % 100
    packet[0x11] = when.isoweekday()
    packet[0x12] = when.day
    packet[0x13] = when.month
    packet[0x1C:0x1E] = source_port.to_bytes(2, "little")
    packet[0x26] = COMMAND_HELLO
    packet[0x20:0x22] = checksum(packet).to_bytes(2, "little")

    return bytes(packet)


def parse_hello(response: bytes) -> DeviceInfo:
    """Parse a hello response into the device identity it carries."""
    if len(response) < 0x40:
        raise ValueError(f"hello response too short: {len(response)} bytes")

    return DeviceInfo(
        devtype=int.from_bytes(response[0x34:0x36], "little"),
        mac=bytes(response[0x3A:0x40][::-1]),
        name=response[0x40:].split(b"\x00")[0].decode(errors="replace"),
        is_locked=bool(response[0x7F]) if len(response) > 0x7F else False,
    )


def pack_command(
    packet_type: int,
    devtype: int,
    mac: bytes,
    device_id: int,
    count: int,
    payload_checksum: int,
    encrypted_payload: bytes,
) -> bytes:
    """Build a command packet around an already-encrypted payload."""
    packet = bytearray(0x38)
    packet[0x00:0x08] = bytes.fromhex("5aa5aa555aa5aa55")
    packet[0x24:0x26] = devtype.to_bytes(2, "little")
    packet[0x26:0x28] = packet_type.to_bytes(2, "little")
    packet[0x28:0x2A] = count.to_bytes(2, "little")
    packet[0x2A:0x30] = mac[::-1]
    packet[0x30:0x34] = device_id.to_bytes(4, "little")
    packet[0x34:0x36] = payload_checksum.to_bytes(2, "little")
    packet.extend(encrypted_payload)
    packet[0x20:0x22] = checksum(packet).to_bytes(2, "little")

    return bytes(packet)


def validate_response(response: bytes) -> None:
    """Check the length and checksum of a command response."""
    if len(response) < 0x30:
        raise ValueError(f"response too short: {len(response)} bytes")

    declared = int.from_bytes(response[0x20:0x22], "little")
    actual = (checksum(response) - sum(response[0x20:0x22])) & 0xFFFF
    if declared != actual:
        raise ValueError(f"response checksum mismatch: {declared:#06x} != {actual:#06x}")


def response_error_code(response: bytes) -> int:
    """Extract the firmware error code from a command response."""
    return int.from_bytes(response[0x22:0x24], "little", signed=True)


def pulses_to_data(pulses: list[int]) -> bytes:
    """Encode a microsecond pulse/gap sequence as a Broadlink IR packet."""
    data = bytearray(4)
    data[0x00] = 0x26

    for pulse in pulses:
        ticks = int(pulse // IR_TICK)
        high, low = divmod(ticks, 256)
        if high:
            data += bytes((0, high))
        data.append(low)

    length = len(data) - 4
    data[0x02:0x04] = length.to_bytes(2, "little")

    return bytes(data)


def data_to_pulses(data: bytes) -> list[int]:
    """Decode a Broadlink IR packet into a microsecond pulse/gap sequence."""
    pulses = []
    index = 4
    end = min(int.from_bytes(data[0x02:0x04], "little") + 4, len(data))

    while index < end:
        ticks = data[index]
        index += 1

        if ticks == 0:
            if index + 1 >= len(data):
                raise ValueError("malformed IR data")
            ticks = data[index] << 8 | data[index + 1]
            index += 2

        pulses.append(int(ticks * IR_TICK))

    return pulses
