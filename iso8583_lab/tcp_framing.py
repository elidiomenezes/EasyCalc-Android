"""TCP stream framing adapters.

This module knows nothing about ISO 8583 fields, specifications, or rules.  It
only turns payloads into framed TCP byte streams and back again.
"""

from __future__ import annotations

import socket


MAX_FRAME = 64 * 1024
FRAMING_CHOICES = ("binary-2", "ascii-4")


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    while size:
        chunk = sock.recv(size)
        if not chunk:
            raise ConnectionError("connection closed before the complete frame arrived")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def _validate_length(size: int) -> int:
    if size == 0 or size > MAX_FRAME:
        raise ValueError(f"invalid frame length: {size}")
    return size


def recv_frame(sock: socket.socket, framing: str) -> bytes:
    if framing == "binary-2":
        size = int.from_bytes(recv_exact(sock, 2), "big")
    elif framing == "ascii-4":
        header = recv_exact(sock, 4)
        if not header.isdigit():
            raise ValueError(f"invalid ASCII length header: {header!r}")
        size = int(header)
    else:
        raise ValueError(f"unsupported TCP framing: {framing}")
    return recv_exact(sock, _validate_length(size))


def send_frame(sock: socket.socket, payload: bytes, framing: str) -> None:
    size = _validate_length(len(payload))
    if framing == "binary-2":
        header = size.to_bytes(2, "big")
    elif framing == "ascii-4":
        if size > 9999:
            raise ValueError("ASCII-4 framing supports at most 9999 payload bytes")
        header = f"{size:04d}".encode("ascii")
    else:
        raise ValueError(f"unsupported TCP framing: {framing}")
    sock.sendall(header + payload)


def add_framing_argument(parser) -> None:
    parser.add_argument(
        "--framing",
        choices=FRAMING_CHOICES,
        default="binary-2",
        help="TCP envelope; independent from the ISO 8583 specification",
    )
