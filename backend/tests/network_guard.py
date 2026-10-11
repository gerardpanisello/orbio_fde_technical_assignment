"""Block real network access in unit tests (NFR-6, AC-23).

A test that silently calls the Anthropic API would be slow, flaky, cost money and need
a key in CI. Patching the socket layer catches it whatever library makes the call.
Loopback stays open because asyncio (on Windows) talks to itself over a socket pair.
"""

import socket
from collections.abc import Callable
from typing import Any

import pytest

_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1", ""})


class NetworkBlocked(RuntimeError):  # noqa: N818 - reads as "the network is blocked"
    """A unit test tried to reach the network.

    Not an OSError on purpose: HTTP clients catch OSError and retry or wrap it, which
    would hide the bug behind a "connection failed" outcome.
    """


def _is_loopback(host: object) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port): the local machine
    if isinstance(host, bytes):
        host = host.decode()
    return isinstance(host, str) and (host in _LOOPBACK_NAMES or host.startswith("127."))


def _host(address: object) -> object:
    return address[0] if isinstance(address, tuple) and address else address


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch connect, connect_ex and getaddrinfo for the duration of one test."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guard(real: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(self: socket.socket, address: Any) -> Any:
            is_ip = self.family in (socket.AF_INET, socket.AF_INET6)
            if is_ip and not _is_loopback(_host(address)):
                raise NetworkBlocked(f"unit tests must not connect to {address!r}")
            return real(self, address)

        return guarded

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_loopback(host):
            raise NetworkBlocked(f"unit tests must not resolve {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guard(real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(real_connect_ex))
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
