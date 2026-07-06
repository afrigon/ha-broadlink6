"""Device transport and session: hello, authentication, commands."""

import random
import socket
import struct
import threading
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import NetworkTimeoutError, ProtocolError, raise_for_error_code
from .protocol import (
    COMMAND_AUTH,
    COMMAND_CONTROL,
    DEFAULT_PORT,
    DeviceInfo,
    pack_command,
    pack_hello,
    parse_hello,
    pulses_to_data,
    response_error_code,
    validate_response,
)

INITIAL_KEY = bytes.fromhex("097628343fe99e23765c1513accf8b02")
INITIAL_VECTOR = bytes.fromhex("562e17996d093d28ddb3ba695a2e6f58")

RETRY_INTERVAL = 1.0


def hello(host: str, port: int = DEFAULT_PORT, timeout: float = 5.0) -> DeviceInfo:
    """Discover the identity of the device at an address or hostname."""
    with _open_socket(timeout) as conn:
        source_port = conn.getsockname()[1]
        response = _exchange(conn, pack_hello(source_port), _resolve(host, port), timeout)
    return parse_hello(response)


class Device:
    """A session with an RM4-series device.

    Call `auth()` once before any command; it negotiates the session key the
    device expects on everything that follows.
    """

    def __init__(
        self,
        host: str,
        devtype: int,
        mac: bytes | str,
        port: int = DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.devtype = devtype
        self.mac = bytes.fromhex(mac.replace(":", "")) if isinstance(mac, str) else mac
        self.timeout = timeout
        self.device_id = 0
        self.count = random.randint(0x8000, 0xFFFF)
        self.key = INITIAL_KEY
        self.lock = threading.Lock()

    def auth(self) -> None:
        """Negotiate a session key with the device."""
        self.device_id = 0
        self.key = INITIAL_KEY

        payload = bytearray(0x50)
        payload[0x04:0x14] = [0x31] * 16
        payload[0x1E] = 0x01
        payload[0x2D] = 0x01
        payload[0x30:0x36] = b"Test 1"

        response = self.send_packet(COMMAND_AUTH, bytes(payload))
        session = self._decrypt(response[0x38:])
        if len(session) < 0x14:
            raise ProtocolError(None, f"auth response too short: {len(session)} bytes")

        self.device_id = int.from_bytes(session[0x00:0x04], "little")
        self.key = session[0x04:0x14]

    def send_pulses(self, pulses: list[int]) -> None:
        """Transmit an IR pulse/gap sequence, given in microseconds."""
        self.send_data(pulses_to_data(pulses))

    def send_data(self, data: bytes) -> None:
        """Transmit a raw Broadlink IR/RF packet."""
        self._command(0x02, data)

    def enter_learning(self) -> None:
        """Put the device in IR learning mode."""
        self._command(0x03)

    def check_data(self) -> bytes:
        """Return the last code captured in learning mode."""
        return self._command(0x04)

    def check_sensors(self) -> dict[str, float]:
        """Read the built-in temperature and humidity sensors."""
        reply = self._command(0x24)
        temperature_whole, temperature_fraction = struct.unpack("<bb", reply[0x00:0x02])
        return {
            "temperature": temperature_whole + temperature_fraction / 100.0,
            "humidity": reply[0x02] + reply[0x03] / 100.0,
        }

    def _command(self, command: int, data: bytes = b"") -> bytes:
        # RM4-series framing: a little-endian length prefix covering the
        # command word, then the command, then its data.
        payload = struct.pack("<HI", len(data) + 4, command) + data
        response = self.send_packet(COMMAND_CONTROL, payload)

        reply = self._decrypt(response[0x38:])
        reply_length = int.from_bytes(reply[0x00:0x02], "little")
        return reply[0x06 : reply_length + 2]

    def send_packet(self, packet_type: int, payload: bytes) -> bytes:
        """Send one command packet and return the validated response."""
        with self.lock:
            self.count = ((self.count + 1) | 0x8000) & 0xFFFF
            padding = (16 - len(payload)) % 16
            packet = pack_command(
                packet_type,
                self.devtype,
                self.mac,
                self.device_id,
                self.count,
                payload_checksum=sum(payload, 0xBEAF) & 0xFFFF,
                encrypted_payload=self._encrypt(payload + bytes(padding)),
            )

            with _open_socket(self.timeout) as conn:
                response = _exchange(
                    conn, packet, _resolve(self.host, self.port), self.timeout
                )

        try:
            validate_response(response)
        except ValueError as err:
            raise ProtocolError(None, str(err)) from err

        raise_for_error_code(response_error_code(response))
        return response

    def _cipher(self) -> Cipher:
        return Cipher(algorithms.AES(self.key), modes.CBC(INITIAL_VECTOR))

    def _encrypt(self, payload: bytes) -> bytes:
        encryptor = self._cipher().encryptor()
        return encryptor.update(payload) + encryptor.finalize()

    def _decrypt(self, payload: bytes) -> bytes:
        decryptor = self._cipher().decryptor()
        return decryptor.update(payload) + decryptor.finalize()


def _open_socket(timeout: float) -> socket.socket:
    conn = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    conn.settimeout(timeout)
    conn.bind(("::", 0))
    return conn


def _resolve(host: str, port: int) -> tuple:
    try:
        info = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_DGRAM)
    except socket.gaierror as err:
        raise NetworkTimeoutError(
            None, f"no IPv6 address for {host!r} (this client is IPv6-only)"
        ) from err
    return info[0][4]


def _exchange(conn: socket.socket, packet: bytes, address: tuple, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NetworkTimeoutError(None, f"no response within {timeout}s")

        conn.settimeout(min(RETRY_INTERVAL, remaining))
        conn.sendto(packet, address)

        try:
            return conn.recvfrom(2048)[0]
        except socket.timeout:
            continue
