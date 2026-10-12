"""The Graph API client (spec 016 T1) behind a small interface, so tests use a fake.

`WhatsAppClient.send` posts one payload and returns WhatsApp's message id. It does not
retry: `GraphError.retryable` says whether trying again can help (timeouts, 429, 5xx)
and the channel owns the retry policy, so it works the same with the fake.
"""

import logging
from typing import Any, Protocol

import httpx

from sazon_screening.whatsapp.payloads import Payload
from sazon_screening.whatsapp.settings import WhatsAppSettings

logger = logging.getLogger("sazon_screening.whatsapp")
TIMEOUT_S = 10.0


class GraphError(Exception):
    """A request the Graph API did not accept. `detail` never contains the phone number
    we sent to (Meta's error messages name the problem, not the recipient)."""

    def __init__(self, detail: str, *, status: int | None, retryable: bool) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.retryable = retryable


class WhatsAppClient(Protocol):
    name: str

    async def send(self, payload: Payload) -> str | None:
        """POST to /messages; WhatsApp's message id (None for a read receipt)."""
        ...

    async def aclose(self) -> None: ...


def as_json(payload: Payload) -> dict[str, Any]:
    return payload.model_dump(mode="json", exclude_none=True)


class GraphWhatsAppClient:
    name = "graph"

    def __init__(self, settings: WhatsAppSettings, http: httpx.AsyncClient | None = None) -> None:
        self._url = settings.messages_url
        self._http = http or httpx.AsyncClient(timeout=TIMEOUT_S)
        self._headers = {"Authorization": f"Bearer {settings.token.get_secret_value()}"}

    async def send(self, payload: Payload) -> str | None:
        try:
            response = await self._http.post(
                self._url, json=as_json(payload), headers=self._headers
            )
        except httpx.TimeoutException as error:
            raise GraphError(
                f"timeout: {type(error).__name__}", status=None, retryable=True
            ) from None
        except httpx.HTTPError as error:
            raise GraphError(
                f"network: {type(error).__name__}", status=None, retryable=True
            ) from None
        if response.status_code >= 400:
            raise GraphError(
                _describe(response),
                status=response.status_code,
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        return _message_id(response)

    async def aclose(self) -> None:
        await self._http.aclose()


def _describe(response: httpx.Response) -> str:
    """Meta's error code and message, e.g. "131030 Recipient phone number not in allowed list"."""
    try:
        error = response.json().get("error", {})
    except ValueError:
        return f"HTTP {response.status_code}"
    code = error.get("code", "?")
    message = error.get("error_data", {}).get("details") or error.get("message", "")
    return f"HTTP {response.status_code}: {code} {message}".strip()


def _message_id(response: httpx.Response) -> str | None:
    try:
        messages = response.json().get("messages") or []
    except ValueError:
        return None
    first = messages[0] if messages and isinstance(messages[0], dict) else {}
    message_id = first.get("id")
    return message_id if isinstance(message_id, str) else None


class FakeWhatsAppClient:
    """Records every payload as the JSON that would be sent; never touches the network.

    `fail_next(n, retryable=...)` makes the next `n` sends raise, to test retries and
    graceful failure (AC-9).
    """

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []  # successful sends, in order
        self.attempts = 0
        self._failures: list[GraphError] = []

    def fail_next(self, n: int = 1, *, retryable: bool = True, status: int = 500) -> None:
        self._failures.extend(
            GraphError(f"HTTP {status}: fake failure", status=status, retryable=retryable)
            for _ in range(n)
        )

    async def send(self, payload: Payload) -> str | None:
        self.attempts += 1
        if self._failures:
            raise self._failures.pop(0)
        body = as_json(payload)
        self.sent.append(body)
        return None if "status" in body else f"wamid.fake.{len(self.sent)}"

    async def aclose(self) -> None:
        return None

    # --- helpers for tests -------------------------------------------------------------

    def messages(self) -> list[dict[str, Any]]:
        """Sent messages only (no read receipts)."""
        return [body for body in self.sent if "status" not in body]

    def receipts(self) -> list[dict[str, Any]]:
        return [body for body in self.sent if body.get("status") == "read"]
