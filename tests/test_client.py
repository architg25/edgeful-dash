from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from edgeful_dash.client import BASE_URL, EdgefulClient
from edgeful_dash.errors import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    EntitlementError,
    RateLimitError,
    ResponseFormatError,
)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response] | httpx.MockTransport,
    *,
    api_key: str = "test-key",
    sleep: Callable[[float], None] | None = None,
) -> EdgefulClient:
    transport = handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return EdgefulClient(api_key=api_key, client=http_client, sleep=sleep)


def test_blank_key_raises_before_any_request_reaches_transport() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={})

    client = make_client(handler, api_key="  ")

    with pytest.raises(ConfigurationError, match="EDGEFUL_API_KEY"):
        client.get("/report", params={"ticker": "RTY"})

    assert seen_requests == []


def test_get_builds_url_sets_auth_headers_and_returns_json_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE_URL}/report?ticker=RTY"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)

    response = client.get("/report", params={"ticker": "RTY"})

    assert response == {"ok": True}


def test_close_closes_owned_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    monkeypatch.setattr("edgeful_dash.client.httpx.Client", lambda: http_client)

    client = EdgefulClient(api_key="test-key")

    client.close()

    assert http_client.is_closed is True


def test_close_leaves_injected_http_client_open() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    client = EdgefulClient(api_key="test-key", client=http_client)

    client.close()

    assert http_client.is_closed is False
    http_client.close()


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, AuthenticationError),
        (403, EntitlementError),
    ],
)
def test_auth_errors_map_without_exposing_key(status_code: int, error_type: type[ApiError]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"code": "EDGEFUL_FORBIDDEN", "detail": "bad test-key secret"},
        )

    client = make_client(handler)

    with pytest.raises(error_type) as exc_info:
        client.get("/report", params={"ticker": "RTY"})

    message = str(exc_info.value)
    assert "test-key" not in message
    if status_code == 403:
        assert "EDGEFUL_FORBIDDEN" in message


def test_rate_limit_retries_twice_before_success() -> None:
    statuses = [429, 429, 200]
    seen_requests: list[httpx.Request] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        status_code = statuses[len(seen_requests) - 1]
        if status_code == 200:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(429, json={"detail": "slow down"})

    client = make_client(handler, sleep=delays.append)

    response = client.get("/report", params={"ticker": "RTY"})

    assert response == {"ok": True}
    assert len(seen_requests) == 3
    assert delays == [1, 2]


def test_three_rate_limits_raise_after_three_attempts() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={"detail": "again"})

    client = make_client(handler, sleep=lambda _: None)

    with pytest.raises(RateLimitError, match="three attempts"):
        client.get("/report", params={"ticker": "RTY"})

    assert attempts == 3


def test_json_array_response_raises_format_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    client = make_client(handler)

    with pytest.raises(ResponseFormatError, match="JSON object"):
        client.get("/report", params={"ticker": "RTY"})


def test_invalid_json_response_raises_format_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{not valid json", headers={"Content-Type": "application/json"})

    client = make_client(handler)

    with pytest.raises(ResponseFormatError, match="valid JSON"):
        client.get("/report", params={"ticker": "RTY"})


def test_non_retryable_http_error_is_raised_once_with_redacted_key() -> None:
    attempts = 0
    detail = "server echoed test-key " + ("x" * 600)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, json={"detail": detail})

    client = make_client(handler)

    with pytest.raises(ApiError) as exc_info:
        client.get("/report", params={"ticker": "RTY"})

    message = str(exc_info.value)
    assert attempts == 1
    assert "test-key" not in message
    assert "[REDACTED]" in message
    assert len(message) < 700


def test_transport_failure_raises_safe_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network broke for test-key", request=request)

    client = make_client(handler)

    with pytest.raises(ApiError) as exc_info:
        client.get("/report", params={"ticker": "RTY"})

    assert (
        str(exc_info.value)
        == "Edgeful API request failed before a response was received."
    )
    assert "test-key" not in str(exc_info.value)


def test_get_sse_event_returns_first_json_data_event_and_closes_response() -> None:
    captured_response: httpx.Response | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_response
        assert str(request.url) == f"{BASE_URL}/live/futures/wip?tickers=ES"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Accept"] == "text/event-stream"
        captured_response = httpx.Response(
            200,
            text=(
                ': ping\n\nevent: update\ndata: {"market_status":"market hours"}\n\n'
                'data: {"ignored":true}\n\n'
            ),
            headers={"Content-Type": "text/event-stream"},
        )
        return captured_response

    client = make_client(handler)

    payload = client.get_sse_event("/live/futures/wip", {"tickers": "ES"})

    assert payload == {"market_status": "market hours"}
    assert captured_response is not None
    assert captured_response.is_closed is True


def test_get_sse_event_rejects_stream_without_data_event() -> None:
    client = make_client(
        lambda _: httpx.Response(
            200,
            text=": ping\n\nevent: update\n\n",
            headers={"Content-Type": "text/event-stream"},
        )
    )

    with pytest.raises(ResponseFormatError, match="ended before"):
        client.get_sse_event("/live/futures/wip", {"tickers": "ES"})


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ("data: {not json}\n\n", "invalid JSON"),
        ("data: [1, 2, 3]\n\n", "JSON object"),
    ],
)
def test_get_sse_event_rejects_invalid_data_event(event: str, message: str) -> None:
    client = make_client(
        lambda _: httpx.Response(
            200,
            text=event,
            headers={"Content-Type": "text/event-stream"},
        )
    )

    with pytest.raises(ResponseFormatError, match=message):
        client.get_sse_event("/live/futures/wip", {"tickers": "ES"})


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, AuthenticationError),
        (403, EntitlementError),
        (500, ApiError),
    ],
)
def test_get_sse_event_maps_http_errors_without_exposing_key(
    status_code: int,
    error_type: type[ApiError],
) -> None:
    client = make_client(
        lambda _: httpx.Response(
            status_code,
            json={"code": "EDGEFUL_ERROR", "detail": "bad test-key secret"},
        )
    )

    with pytest.raises(error_type) as exc_info:
        client.get_sse_event("/live/futures/wip", {"tickers": "ES"})

    assert "test-key" not in str(exc_info.value)


def test_get_sse_event_retries_rate_limits_before_success() -> None:
    statuses = [429, 429, 200]
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        status_code = statuses[attempts]
        attempts += 1
        if status_code == 200:
            return httpx.Response(
                200,
                text='data: {"ok":true}\n\n',
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(429, json={"detail": "slow down"})

    client = make_client(handler, sleep=delays.append)

    payload = client.get_sse_event("/live/futures/wip", {"tickers": "ES"})

    assert payload == {"ok": True}
    assert attempts == 3
    assert delays == [1, 2]


def test_get_sse_event_raises_after_three_rate_limits() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={"detail": "again"})

    client = make_client(handler, sleep=lambda _: None)

    with pytest.raises(RateLimitError, match="three attempts"):
        client.get_sse_event("/live/futures/wip", {"tickers": "ES"})

    assert attempts == 3


def test_get_sse_event_transport_failure_raises_safe_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network broke for test-key", request=request)

    client = make_client(handler)

    with pytest.raises(ApiError, match="live stream") as exc_info:
        client.get_sse_event("/live/futures/wip", {"tickers": "ES"})

    assert "test-key" not in str(exc_info.value)
