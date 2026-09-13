from __future__ import annotations

import socket
import struct

from .protocol import Message, ProtocolError, encode_error

MAX_FRAME_LENGTH = 1024 * 1024


def read_exact(sock: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Unity worker disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_frame(sock: socket.socket) -> bytes:
    length = struct.unpack("<i", read_exact(sock, 4))[0]
    if length < 1 or length > MAX_FRAME_LENGTH:
        raise ProtocolError(f"Invalid frame length {length}")
    return read_exact(sock, length)


def send_frame(sock: socket.socket, payload: bytes) -> None:
    if not payload or len(payload) > MAX_FRAME_LENGTH:
        raise ProtocolError(f"Invalid outgoing frame length {len(payload)}")
    sock.sendall(struct.pack("<i", len(payload)) + payload)


def send_error(sock: socket.socket, message: str) -> None:
    try:
        send_frame(sock, encode_error(message))
    except OSError:
        pass


def expect_message(payload: bytes, expected: Message) -> None:
    if payload != bytes((expected,)):
        actual = payload[0] if payload else None
        raise ProtocolError(f"Expected {expected.name}, received {actual}")
