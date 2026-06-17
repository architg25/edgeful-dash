# Edgeful CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure Python CLI that fetches Edgeful's RTY previous-day's-range report, prints available headline values, and saves the complete JSON response.

**Architecture:** Keep HTTP transport, report-specific behavior, and CLI coordination in separate modules. Inject HTTP and timing dependencies so unit tests exercise real request construction and retry behavior without network access. Read credentials only from the environment and defer the live smoke test until the user places the key in the ignored `.env` file.

**Tech Stack:** Python 3.12, uv, httpx, python-dotenv, argparse, pytest

---

## File Map

- `pyproject.toml`: package metadata, dependencies, console entry point, and pytest configuration.
- `.gitignore`: credential, environment, cache, build, and generated-response exclusions.
- `.env.example`: committed credential placeholder.
- `.env`: ignored local credential placeholder.
- `src/edgeful_dash/errors.py`: configuration and API exception types.
- `src/edgeful_dash/client.py`: authenticated transport, response validation, and bounded `429` retries.
- `src/edgeful_dash/reports.py`: previous-day's-range request construction, summary formatting, and JSON persistence.
- `src/edgeful_dash/cli.py`: argument parsing, environment loading, orchestration, and exit codes.
- `tests/test_client.py`: transport, security, status mapping, and retry tests.
- `tests/test_reports.py`: dates, request shape, summaries, and persistence tests.
- `tests/test_cli.py`: end-to-end CLI coordination tests with an in-memory fake client.
- `README.md`: installation, credentials, commands, output, limits, and troubleshooting.

### Task 1: Scaffold the package and protect local credentials

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `.env`
- Create: `README.md`
- Create: `data/raw/.gitkeep`
- Create: `src/edgeful_dash/__init__.py`

- [ ] **Step 1: Add the project metadata**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "edgeful-dash"
version = "0.1.0"
description = "A small, testable CLI for the Edgeful API."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.27,<1",
  "python-dotenv>=1,<2",
]

[project.scripts]
edgeful-dash = "edgeful_dash.cli:main"

[dependency-groups]
dev = [
  "pytest>=8,<9",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Add credential and generated-file exclusions**

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
*.egg-info/
dist/
build/
data/raw/*.json
```

- [ ] **Step 3: Add committed and local environment placeholders**

`.env.example`:

```dotenv
EDGEFUL_API_KEY=
```

`.env`:

```dotenv
EDGEFUL_API_KEY=
```

- [ ] **Step 4: Add package and output-directory markers**

`README.md`:

```markdown
# edgeful-dash
```

`src/edgeful_dash/__init__.py`:

```python
"""Edgeful API command-line client."""
```

`data/raw/.gitkeep` is an empty file.

- [ ] **Step 5: Verify the credential file is ignored**

Run:

```bash
git check-ignore -v .env
git status --short
```

Expected: `.env` is matched by `.gitignore`; `.env` does not appear in `git status`.

- [ ] **Step 6: Install the locked environment**

Run:

```bash
uv sync --dev
```

Expected: exit `0`, `.venv` and `uv.lock` are created, and dependencies resolve.

- [ ] **Step 7: Commit the scaffold**

```bash
git add .gitignore .env.example README.md pyproject.toml uv.lock data/raw/.gitkeep src/edgeful_dash/__init__.py
git commit -m "chore: scaffold Edgeful CLI project"
```

### Task 2: Implement authenticated transport with bounded retries

**Files:**
- Create: `src/edgeful_dash/errors.py`
- Create: `src/edgeful_dash/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing transport tests**

```python
import json

import httpx
import pytest

from edgeful_dash.client import EdgefulClient
from edgeful_dash.errors import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    EntitlementError,
    RateLimitError,
    ResponseFormatError,
)


def make_http_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rejects_blank_api_key_before_request():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ConfigurationError, match="EDGEFUL_API_KEY"):
        EdgefulClient(" ", http_client=make_http_client(handler))

    assert requests == []


def test_builds_authenticated_request_without_exposing_key():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"summary": {}})

    secret = "ef_live_do_not_print"
    client = EdgefulClient(secret, http_client=make_http_client(handler))

    result = client.get("/report", {"ticker": "RTY"})

    assert result == {"summary": {}}
    assert str(seen["request"].url) == "https://api.edgeful.com/report?ticker=RTY"
    assert seen["request"].headers["Authorization"] == f"Bearer {secret}"


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, AuthenticationError),
        (403, EntitlementError),
    ],
)
def test_maps_authentication_and_entitlement_errors(status, error_type):
    def handler(request):
        return httpx.Response(
            status,
            json={"code": "history_range_exceeded", "detail": "upgrade required"},
        )

    client = EdgefulClient(
        "ef_live_secret",
        http_client=make_http_client(handler),
    )

    with pytest.raises(error_type) as raised:
        client.get("/report", {})

    assert "ef_live_secret" not in str(raised.value)


def test_retries_429_twice_then_succeeds():
    attempts = []
    delays = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(200, json={"summary": {"ok": True}})

    client = EdgefulClient(
        "ef_live_secret",
        http_client=make_http_client(handler),
        sleep=delays.append,
    )

    assert client.get("/report", {}) == {"summary": {"ok": True}}
    assert len(attempts) == 3
    assert delays == [1, 2]


def test_raises_after_three_429_responses():
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(429, json={"detail": "slow down"})

    client = EdgefulClient(
        "ef_live_secret",
        http_client=make_http_client(handler),
        sleep=lambda delay: None,
    )

    with pytest.raises(RateLimitError, match="three attempts"):
        client.get("/report", {})

    assert len(attempts) == 3


def test_rejects_non_object_json():
    def handler(request):
        return httpx.Response(200, content=json.dumps(["unexpected"]))

    client = EdgefulClient(
        "ef_live_secret",
        http_client=make_http_client(handler),
    )

    with pytest.raises(ResponseFormatError, match="JSON object"):
        client.get("/report", {})


def test_rejects_invalid_json():
    def handler(request):
        return httpx.Response(200, content=b"not-json")

    client = EdgefulClient(
        "ef_live_secret",
        http_client=make_http_client(handler),
    )

    with pytest.raises(ResponseFormatError, match="valid JSON"):
        client.get("/report", {})


def test_does_not_retry_other_errors_and_redacts_key():
    attempts = []
    secret = "ef_live_secret"

    def handler(request):
        attempts.append(request)
        return httpx.Response(500, text=f"upstream echoed {secret}")

    client = EdgefulClient(secret, http_client=make_http_client(handler))

    with pytest.raises(ApiError) as raised:
        client.get("/report", {})

    assert len(attempts) == 1
    assert secret not in str(raised.value)
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run:

```bash
uv run pytest tests/test_client.py
```

Expected: failure because `edgeful_dash.client` and `edgeful_dash.errors` do not exist.

- [ ] **Step 3: Add the exception types**

```python
class EdgefulError(Exception):
    """Base class for expected Edgeful client failures."""


class ConfigurationError(EdgefulError):
    """Raised when local configuration is incomplete."""


class ApiError(EdgefulError):
    """Raised when Edgeful returns an unexpected API error."""


class AuthenticationError(ApiError):
    """Raised when the API key is missing, malformed, or revoked."""


class EntitlementError(ApiError):
    """Raised when the account plan does not permit a request."""


class RateLimitError(ApiError):
    """Raised after bounded rate-limit retries are exhausted."""


class ResponseFormatError(ApiError):
    """Raised when a successful response has an unexpected body."""
```

- [ ] **Step 4: Add the minimal transport implementation**

```python
from collections.abc import Callable, Mapping
import time
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


class EdgefulClient:
    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ConfigurationError(
                "EDGEFUL_API_KEY is missing. Add it to the local .env file."
            )
        if max_attempts != 3:
            raise ValueError("EdgefulClient uses exactly three total attempts")

        self._api_key = normalized_key
        self._http_client = http_client or httpx.Client(timeout=30)
        self._sleep = sleep
        self._max_attempts = max_attempts

    def get(
        self,
        path: str,
        params: Mapping[str, str],
    ) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            response = self._http_client.get(
                f"{BASE_URL}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
            )

            if response.status_code != 429:
                return self._decode_response(response)

            if attempt < self._max_attempts - 1:
                self._sleep(2**attempt)

        raise RateLimitError(
            "Edgeful rate limit remained active after three attempts."
        )

    def _decode_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise AuthenticationError(
                "Edgeful rejected the API key. Check that it is loaded and active."
            )
        if response.status_code == 403:
            detail = self._safe_error_detail(response)
            raise EntitlementError(f"Edgeful plan restriction: {detail}")
        if response.is_error:
            detail = self._safe_error_detail(response)
            raise ApiError(f"Edgeful returned HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as error:
            raise ResponseFormatError(
                "Edgeful returned HTTP 200 without valid JSON."
            ) from error

        if not isinstance(payload, dict):
            raise ResponseFormatError(
                "Edgeful returned HTTP 200 without a JSON object."
            )
        return payload

    def _safe_error_detail(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            detail = response.text
        else:
            if isinstance(payload, dict):
                detail = str(
                    payload.get("code")
                    or payload.get("detail")
                    or payload.get("app_exception")
                    or "request failed"
                )
            else:
                detail = "request failed"

        return detail.replace(self._api_key, "[redacted]")[:500]
```

- [ ] **Step 5: Run the transport tests**

Run:

```bash
uv run pytest tests/test_client.py
```

Expected: all transport tests pass.

- [ ] **Step 6: Commit the transport**

```bash
git add src/edgeful_dash/errors.py src/edgeful_dash/client.py tests/test_client.py
git commit -m "feat: add authenticated Edgeful transport"
```

### Task 3: Implement the previous-day's-range report boundary

**Files:**
- Create: `src/edgeful_dash/reports.py`
- Create: `tests/test_reports.py`

- [ ] **Step 1: Write failing report tests**

```python
from datetime import date
import json

import pytest

from edgeful_dash.reports import (
    build_previous_days_range_request,
    default_date_range,
    save_response,
    summarize_previous_days_range,
)


def test_default_date_range_uses_completed_days():
    assert default_date_range(date(2026, 6, 17)) == (
        date(2026, 3, 17),
        date(2026, 6, 16),
    )


def test_builds_previous_days_range_request():
    path, params = build_previous_days_range_request(
        ticker="rty",
        market_type="futures",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
        start_time="09:30:00",
        end_time="16:00:00",
        timezone="America/New_York",
    )

    assert path == (
        "/report_calculation/previous-days-range-standard/futures/RTY"
    )
    assert params == {
        "start_date": "2026-03-17",
        "end_date": "2026-06-16",
        "start_time": "09:30:00",
        "end_time": "16:00:00",
        "timezone": "America/New_York",
    }


def test_rejects_reversed_date_range():
    with pytest.raises(ValueError, match="start date"):
        build_previous_days_range_request(
            ticker="RTY",
            market_type="futures",
            start_date=date(2026, 6, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


def test_summarizes_only_present_fields():
    payload = {
        "startDate": "2026-03-17",
        "endDate": "2026-06-16",
        "summary": {
            "prevDayHigh": {"count": 31, "percentage": 52.5},
            "prevDayLow": {"count": 28, "percentage": 47.5},
            "prevDayHighGreen": {"count": 20, "percentage": 64.5},
        },
    }

    assert summarize_previous_days_range(payload) == [
        "Date range: 2026-03-17 to 2026-06-16",
        "Previous-day high: count=31, percentage=52.5",
        "Previous-day low: count=28, percentage=47.5",
        "Previous-day high, green close: count=20, percentage=64.5",
    ]


def test_saves_unmodified_response_with_deterministic_name(tmp_path):
    payload = {"summary": {"prevDayHigh": {"count": 1}}}

    path = save_response(
        payload,
        output_dir=tmp_path,
        market_type="futures",
        ticker="RTY",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
    )

    assert path.name == (
        "previous-days-range_futures_RTY_2026-03-17_2026-06-16.json"
    )
    assert json.loads(path.read_text()) == payload
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run:

```bash
uv run pytest tests/test_reports.py
```

Expected: failure because `edgeful_dash.reports` does not exist.

- [ ] **Step 3: Add the report implementation**

```python
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any


def default_date_range(today: date | None = None) -> tuple[date, date]:
    current_date = today or date.today()
    return current_date - timedelta(days=92), current_date - timedelta(days=1)


def build_previous_days_range_request(
    *,
    ticker: str,
    market_type: str,
    start_date: date,
    end_date: date,
    start_time: str,
    end_time: str,
    timezone: str,
) -> tuple[str, dict[str, str]]:
    if start_date > end_date:
        raise ValueError("start date must not be after end date")

    normalized_ticker = ticker.strip().upper().replace("/", "")
    normalized_market_type = market_type.strip().lower()
    if not normalized_ticker:
        raise ValueError("ticker must not be blank")
    if not normalized_market_type:
        raise ValueError("market type must not be blank")

    path = (
        "/report_calculation/previous-days-range-standard/"
        f"{normalized_market_type}/{normalized_ticker}"
    )
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone,
    }
    return path, params


def summarize_previous_days_range(payload: dict[str, Any]) -> list[str]:
    lines = []
    start_date = payload.get("startDate")
    end_date = payload.get("endDate")
    if start_date is not None and end_date is not None:
        lines.append(f"Date range: {start_date} to {end_date}")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return lines

    labels = {
        "prevDayHigh": "Previous-day high",
        "prevDayLow": "Previous-day low",
        "prevDayHighGreen": "Previous-day high, green close",
        "prevDayHighRed": "Previous-day high, red close",
        "prevDayLowGreen": "Previous-day low, green close",
        "prevDayLowRed": "Previous-day low, red close",
    }
    for key, label in labels.items():
        if key in summary:
            lines.append(_format_metric(label, summary[key]))
    return lines


def _format_metric(label: str, value: Any) -> str:
    if not isinstance(value, dict):
        return f"{label}: {value}"

    parts = []
    if "count" in value:
        parts.append(f"count={value['count']}")
    if "percentage" in value:
        parts.append(f"percentage={value['percentage']}")
    if not parts:
        return f"{label}: {value}"
    return f"{label}: {', '.join(parts)}"


def save_response(
    payload: dict[str, Any],
    *,
    output_dir: Path,
    market_type: str,
    ticker: str,
    start_date: date,
    end_date: date,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.strip().upper().replace("/", "-")
    safe_market_type = market_type.strip().lower()
    filename = (
        "previous-days-range_"
        f"{safe_market_type}_{safe_ticker}_"
        f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    )
    path = output_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path
```

- [ ] **Step 4: Run report tests**

Run:

```bash
uv run pytest tests/test_reports.py
```

Expected: all report tests pass.

- [ ] **Step 5: Commit the report boundary**

```bash
git add src/edgeful_dash/reports.py tests/test_reports.py
git commit -m "feat: add previous-day range report support"
```

### Task 4: Implement the CLI orchestration

**Files:**
- Create: `src/edgeful_dash/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
from datetime import date
from io import StringIO
import json

from edgeful_dash.cli import run
from edgeful_dash.errors import EntitlementError


class FakeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, params))
        return {
            "startDate": "2026-03-17",
            "endDate": "2026-06-16",
            "summary": {
                "prevDayHigh": {"count": 31, "percentage": 52.5},
                "prevDayLow": {"count": 28, "percentage": 47.5},
            },
        }


def test_missing_key_fails_before_client_creation(tmp_path):
    created = []
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range", "--output-dir", str(tmp_path)],
        environ={},
        load_environment=lambda: None,
        client_factory=lambda api_key: created.append(api_key),
        stderr=stderr,
        today=date(2026, 6, 17),
    )

    assert exit_code == 2
    assert created == []
    assert "EDGEFUL_API_KEY" in stderr.getvalue()


def test_default_command_fetches_summarizes_and_saves(tmp_path):
    clients = []
    stdout = StringIO()

    def client_factory(api_key):
        client = FakeClient(api_key)
        clients.append(client)
        return client

    exit_code = run(
        ["previous-days-range", "--output-dir", str(tmp_path)],
        environ={"EDGEFUL_API_KEY": "ef_live_secret"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        today=date(2026, 6, 17),
    )

    assert exit_code == 0
    assert clients[0].api_key == "ef_live_secret"
    path, params = clients[0].calls[0]
    assert path.endswith("/futures/RTY")
    assert params["start_date"] == "2026-03-17"
    assert params["end_date"] == "2026-06-16"
    assert "Previous-day high: count=31, percentage=52.5" in stdout.getvalue()
    saved = list(tmp_path.glob("*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())["summary"]["prevDayLow"]["count"] == 28
    assert "ef_live_secret" not in stdout.getvalue()


def test_invalid_date_fails_without_calling_client(tmp_path):
    client = FakeClient("ef_live_secret")
    stderr = StringIO()

    exit_code = run(
        [
            "previous-days-range",
            "--start-date",
            "2026-06-17",
            "--end-date",
            "2026-06-16",
            "--output-dir",
            str(tmp_path),
        ],
        environ={"EDGEFUL_API_KEY": "ef_live_secret"},
        load_environment=lambda: None,
        client_factory=lambda api_key: client,
        stderr=stderr,
    )

    assert exit_code == 2
    assert client.calls == []
    assert "start date" in stderr.getvalue()


def test_expected_api_error_has_concise_message(tmp_path):
    stderr = StringIO()

    class DeniedClient:
        def get(self, path, params):
            raise EntitlementError(
                "Edgeful plan restriction: history_range_exceeded"
            )

    exit_code = run(
        ["previous-days-range", "--output-dir", str(tmp_path)],
        environ={"EDGEFUL_API_KEY": "ef_live_secret"},
        load_environment=lambda: None,
        client_factory=lambda api_key: DeniedClient(),
        stderr=stderr,
        today=date(2026, 6, 17),
    )

    assert exit_code == 2
    assert stderr.getvalue().strip() == (
        "Edgeful plan restriction: history_range_exceeded"
    )
    assert "Traceback" not in stderr.getvalue()
    assert "ef_live_secret" not in stderr.getvalue()
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

Run:

```bash
uv run pytest tests/test_cli.py
```

Expected: failure because `edgeful_dash.cli` does not exist.

- [ ] **Step 3: Add the CLI implementation**

```python
import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import date
import os
from pathlib import Path
import sys
from typing import TextIO

from dotenv import load_dotenv

from edgeful_dash.client import EdgefulClient
from edgeful_dash.errors import EdgefulError
from edgeful_dash.reports import (
    build_previous_days_range_request,
    default_date_range,
    save_response,
    summarize_previous_days_range,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edgeful-dash")
    subparsers = parser.add_subparsers(dest="command", required=True)
    report = subparsers.add_parser("previous-days-range")
    report.add_argument("--ticker", default="RTY")
    report.add_argument("--market-type", default="futures")
    report.add_argument("--start-date", type=date.fromisoformat)
    report.add_argument("--end-date", type=date.fromisoformat)
    report.add_argument("--start-time", default="09:30:00")
    report.add_argument("--end-time", default="16:00:00")
    report.add_argument("--timezone", default="America/New_York")
    report.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    load_environment: Callable[[], object] = load_dotenv,
    client_factory: Callable[[str], EdgefulClient] = EdgefulClient,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    today: date | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    load_environment()

    api_key = environ.get("EDGEFUL_API_KEY", "").strip()
    if not api_key:
        print(
            "EDGEFUL_API_KEY is missing. Add it to the local .env file.",
            file=stderr,
        )
        return 2

    default_start, default_end = default_date_range(today)
    start_date = args.start_date or default_start
    end_date = args.end_date or default_end

    try:
        path, params = build_previous_days_range_request(
            ticker=args.ticker,
            market_type=args.market_type,
            start_date=start_date,
            end_date=end_date,
            start_time=args.start_time,
            end_time=args.end_time,
            timezone=args.timezone,
        )
        payload = client_factory(api_key).get(path, params)
        output_path = save_response(
            payload,
            output_dir=args.output_dir,
            market_type=args.market_type,
            ticker=args.ticker,
            start_date=start_date,
            end_date=end_date,
        )
    except (EdgefulError, OSError, ValueError) as error:
        print(str(error), file=stderr)
        return 2

    for line in summarize_previous_days_range(payload):
        print(line, file=stdout)
    print(f"Saved response: {output_path}", file=stdout)
    return 0


def main() -> None:
    raise SystemExit(run())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py
```

Expected: all CLI tests pass.

- [ ] **Step 5: Run the complete unit suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass with no warnings or errors.

- [ ] **Step 6: Commit the CLI**

```bash
git add src/edgeful_dash/cli.py tests/test_cli.py
git commit -m "feat: add previous-day range CLI"
```

### Task 5: Document usage and verify credential-safe local behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the README**

```markdown
# edgeful-dash

A small Python CLI for fetching Edgeful report data and saving the complete JSON
response for later analysis.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- An Edgeful API key from <https://www.edgeful.com/api-dashboard>

## Setup

```bash
uv sync --dev
```

Open `.env` and paste the key after the equals sign:

```dotenv
EDGEFUL_API_KEY=ef_live_your_key_here
```

Do not commit `.env` or paste the key into chat, shell history, screenshots, or
logs. Edgeful shows the plaintext key only once.

## Fetch the default report

```bash
uv run edgeful-dash previous-days-range
```

The default request uses:

- report: previous day's range;
- ticker: RTY;
- market type: futures;
- dates: the previous 92 completed calendar days;
- session: 09:30–16:00 America/New_York.

Responses are saved under `data/raw/`.

## Override request values

```bash
uv run edgeful-dash previous-days-range \
  --ticker RTY \
  --market-type futures \
  --start-date 2026-03-17 \
  --end-date 2026-06-16 \
  --start-time 09:30:00 \
  --end-time 16:00:00 \
  --timezone America/New_York \
  --output-dir data/raw
```

## Tests

```bash
uv run pytest
```

Unit tests use an in-memory HTTP transport and do not call Edgeful.

## API behavior

- Base URL: `https://api.edgeful.com`
- Authentication: `Authorization: Bearer <API key>`
- `401`: key missing, malformed, or revoked
- `403`: plan, ticker, report, live-data, or history restriction
- `429`: rate limited; the client retries twice with exponential backoff

Current documented limits are 30 requests per 60 seconds, 5 requests per 5
seconds, and 500 requests per hour. Plan entitlements determine available
reports, tickers, history, live data, and row-level detail.
```

- [ ] **Step 2: Verify safe failure without the key**

Run:

```bash
env -u EDGEFUL_API_KEY uv run edgeful-dash previous-days-range
```

Expected: exit `2`; message instructs the user to populate `.env`; no traceback
and no request is attempted.

Because `.env` exists locally, temporarily leave its value blank for this check.

- [ ] **Step 3: Verify formatting and repository state**

Run:

```bash
uv run pytest
git diff --check
git status --short
git check-ignore -v .env data/raw/example.json
```

Expected: tests pass; no whitespace errors; `.env` and generated JSON are
ignored; only intended documentation changes are uncommitted.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md
git commit -m "docs: document Edgeful CLI usage"
```

### Task 6: Run the live smoke test after local key entry

**Files:**
- Local-only input: `.env`
- Generated and ignored: `data/raw/previous-days-range_futures_RTY_<start>_<end>.json`

- [ ] **Step 1: Pause for local credential entry**

Tell the user:

```text
Open /Users/architg/Git/edgeful-dash/.env, paste your key after
EDGEFUL_API_KEY=, save it, and reply done. Do not paste the key into chat.
```

Do not proceed until the user confirms.

- [ ] **Step 2: Verify presence without printing the key**

Run:

```bash
uv run python -c "from dotenv import dotenv_values; value = dotenv_values('.env').get('EDGEFUL_API_KEY', ''); raise SystemExit(0 if value and value.startswith('ef_live_') else 1)"
```

Expected: exit `0` with no output.

- [ ] **Step 3: Run the live report**

Run:

```bash
uv run edgeful-dash previous-days-range
```

Expected: exit `0`, returned date range and available summary metrics are
printed, and one JSON response is saved under `data/raw/`.

If Edgeful returns `401`, stop and report an authentication problem. If it
returns `403`, report the exact non-secret entitlement code. If it returns
`429` after three total attempts, stop and report rate limiting. Do not exceed
three attempts for any one failure.

- [ ] **Step 4: Inspect the saved response without exposing credentials**

Run:

```bash
latest_file=$(find data/raw -name '*.json' -type f -print | sort | tail -1)
test -n "$latest_file"
python3 -m json.tool "$latest_file" >/dev/null
```

Expected: exit `0`; the saved file contains valid JSON.

- [ ] **Step 5: Run final verification**

Run:

```bash
uv run pytest
git diff --check
git status --short
```

Expected: tests pass; no whitespace errors; `.env` and response JSON remain
ignored; the worktree is clean after committed source and documentation.
