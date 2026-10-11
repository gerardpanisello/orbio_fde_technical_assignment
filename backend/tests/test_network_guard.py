"""T4: unit tests never reach the network (NFR-6, AC-23).

The guard lives in `tests/conftest.py` and is on for every test except `live` ones.
"""

import socket

import anyio
import pytest
import sniffio

from tests.network_guard import NetworkBlocked


@pytest.mark.ac("003:AC-23")
def test_outbound_connection_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 443), timeout=1)


@pytest.mark.ac("003:AC-23")
def test_connecting_to_a_public_ip_is_blocked() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkBlocked):
            sock.connect(("93.184.215.14", 443))
        with pytest.raises(NetworkBlocked):
            sock.connect_ex(("93.184.215.14", 443))
    finally:
        sock.close()


@pytest.mark.ac("003:AC-23")
def test_loopback_socketpair_still_works() -> None:
    # asyncio's self-pipe on Windows is a loopback socket pair: it must keep working.
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ping")
        assert right.recv(4) == b"ping"


@pytest.mark.ac("003:AC-23")
@pytest.mark.anyio
async def test_async_tests_run_on_asyncio() -> None:
    await anyio.sleep(0)
    assert sniffio.current_async_library() == "asyncio"


@pytest.mark.live
def test_live_tests_are_skipped_without_a_key() -> None:
    """Never runs in CI: collection skips it unless the key AND LLM_MODE=anthropic are set."""
