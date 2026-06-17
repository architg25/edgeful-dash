from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from edgeful_dash.errors import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    EntitlementError,
    RateLimitError,
    ResponseFormatError,
)

BASE_URL = "https://api.edgeful.com"
_MAX_ATTEMPTS = 3
_MAX_DETAIL_LENGTH = 500


class EdgefulClient:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client()
        self._sleep = sleep or time.sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        api_key = self._validated_api_key()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.get(
                    self._build_url(path),
                    params=dict(params),
                    headers=headers,
                )
            except httpx.RequestError as error:
                raise ApiError(
                    "Edgeful API request failed before a response was received."
                ) from error
            if response.status_code == 429:
                if attempt == _MAX_ATTEMPTS:
                    raise RateLimitError(
                        "Edgeful API rate limit persisted after three attempts."
                    )
                self._sleep(attempt)
                continue

            self._raise_for_status(response, api_key)
            return self._parse_object_response(response)

        raise AssertionError("Unreachable")

    def get_sse_event(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        api_key = self._validated_api_key()
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            retry = False
            try:
                with self._client.stream(
                    "GET",
                    self._build_url(path),
                    params=dict(params),
                    headers=headers,
                ) as response:
                    if response.status_code == 429:
                        if attempt == _MAX_ATTEMPTS:
                            raise RateLimitError(
                                "Edgeful API rate limit persisted after three attempts."
                            )
                        retry = True
                    else:
                        if response.status_code >= 400:
                            response.read()
                        self._raise_for_status(response, api_key)
                        return self._parse_sse_object(response)
            except httpx.RequestError as error:
                raise ApiError(
                    "Edgeful API live stream failed before a complete event was received."
                ) from error

            if retry:
                self._sleep(attempt)

        raise AssertionError("Unreachable")

    def _validated_api_key(self) -> str:
        api_key = self._api_key.strip()
        if not api_key:
            raise ConfigurationError(
                "EDGEFUL_API_KEY is required. Set it in your environment or local .env file."
            )
        return api_key

    def _build_url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def _parse_object_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ResponseFormatError(
                "Edgeful API returned an invalid response; expected valid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseFormatError(
                "Edgeful API returned an invalid response; expected a JSON object."
            )
        return payload

    def _parse_sse_object(self, response: httpx.Response) -> dict[str, Any]:
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw_payload = line[5:].lstrip()
            if not raw_payload:
                continue
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError as error:
                raise ResponseFormatError(
                    "Edgeful API live stream returned invalid JSON."
                ) from error
            if not isinstance(payload, dict):
                raise ResponseFormatError(
                    "Edgeful API live stream returned an invalid event; "
                    "expected a JSON object."
                )
            return payload
        raise ResponseFormatError(
            "Edgeful API live stream ended before returning a JSON data event."
        )

    def _raise_for_status(self, response: httpx.Response, api_key: str) -> None:
        if response.status_code == 401:
            raise AuthenticationError("Edgeful API rejected the configured API key.")

        if response.status_code == 403:
            detail = self._safe_detail(response, api_key)
            raise EntitlementError(
                f"Edgeful API denied access to this resource. {detail}".strip()
            )

        if response.status_code >= 400:
            detail = self._safe_detail(response, api_key)
            raise ApiError(
                f"Edgeful API request failed with status {response.status_code}. {detail}".strip()
            )

    def _safe_detail(self, response: httpx.Response, api_key: str) -> str:
        detail = ""
        try:
            payload = response.json()
        except json.JSONDecodeError:
            detail = response.text
        else:
            if isinstance(payload, dict):
                parts: list[str] = []
                code = payload.get("code")
                if isinstance(code, str) and code:
                    parts.append(f"code={code}")
                message = payload.get("detail")
                if isinstance(message, str) and message:
                    parts.append(message)
                detail = "; ".join(parts) if parts else json.dumps(payload)
            else:
                detail = json.dumps(payload)

        redacted = detail.replace(api_key, "[REDACTED]").strip()
        if not redacted:
            return ""
        return redacted[:_MAX_DETAIL_LENGTH]
