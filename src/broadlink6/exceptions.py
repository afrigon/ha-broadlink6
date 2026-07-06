"""Errors reported by Broadlink devices or raised by this client."""


class BroadlinkError(Exception):
    """Base error, carrying the firmware error code when one exists."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"[{code}] {message}" if code is not None else message)
        self.code = code
        self.message = message


class AuthenticationError(BroadlinkError):
    """The device rejected the authentication handshake."""


class AuthorizationError(BroadlinkError):
    """The device refused the command (expired control key or locked device)."""


class NetworkTimeoutError(BroadlinkError):
    """The device did not answer within the allowed time."""


class ProtocolError(BroadlinkError):
    """A response failed structural validation."""


FIRMWARE_ERRORS: dict[int, tuple[type[BroadlinkError], str]] = {
    -1: (AuthenticationError, "authentication failed"),
    -2: (BroadlinkError, "you have been logged out"),
    -3: (BroadlinkError, "the device is offline"),
    -4: (BroadlinkError, "command not supported"),
    -5: (BroadlinkError, "the device storage is full"),
    -6: (BroadlinkError, "structure is abnormal"),
    -7: (AuthorizationError, "control key is expired"),
    -8: (BroadlinkError, "send error"),
    -9: (BroadlinkError, "write error"),
    -10: (BroadlinkError, "read error"),
    -4012: (AuthorizationError, "device control id error"),
}


def raise_for_error_code(code: int) -> None:
    """Raise the matching error for a nonzero firmware error code."""
    if not code:
        return
    error_type, message = FIRMWARE_ERRORS.get(code, (BroadlinkError, "unknown error"))
    raise error_type(code, message)
