from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path

import pytest

from edgeful_dash.errors import EntitlementError


class FakeClient:
    def __init__(self, api_key: str, *, payload: dict | None = None, error: Exception | None = None) -> None:
        self.api_key = api_key
        self.payload = payload or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def get(self, path: str, params: dict[str, str]) -> dict:
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error
        return self.payload

    def close(self) -> None:
        self.closed = True


def test_run_returns_2_when_api_key_is_missing() -> None:
    from edgeful_dash.cli import run

    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(api_key)
        created_clients.append(client)
        return client

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range"],
        environ={},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert created_clients == []
    assert "EDGEFUL_API_KEY" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_run_executes_default_previous_days_range_command(tmp_path: Path) -> None:
    from edgeful_dash.cli import run

    payload = {
        "startDate": "2026-03-17",
        "endDate": "2026-06-16",
        "summary": {
            "prevDayHigh": {"count": 31, "percentage": 52.5},
            "prevDayLow": {"count": 28, "percentage": 47.5},
        },
    }
    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(api_key, payload=payload)
        created_clients.append(client)
        return client

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range", "--output-dir", str(tmp_path)],
        environ={"EDGEFUL_API_KEY": "  fake-secret-key  "},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
        today=date(2026, 6, 17),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert len(created_clients) == 1
    client = created_clients[0]
    assert client.api_key == "fake-secret-key"
    assert client.closed is True
    assert client.calls == [
        (
            "/report_calculation/previous-days-range-standard/futures/RTY",
            {
                "start_date": "2026-03-17",
                "end_date": "2026-06-16",
                "start_time": "09:30:00",
                "end_time": "16:00:00",
                "timezone": "America/New_York",
            },
        )
    ]

    output = stdout.getvalue()
    assert "Previous-day high: count=31, percentage=52.5" in output
    assert "Previous-day low: count=28, percentage=47.5" in output
    assert "fake-secret-key" not in output
    saved_files = list(tmp_path.glob("*.json"))
    assert len(saved_files) == 1
    assert f"Saved response: {saved_files[0]}" in output


def test_run_rejects_reversed_explicit_dates_before_client_get(tmp_path: Path) -> None:
    from edgeful_dash.cli import run

    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(api_key)
        created_clients.append(client)
        return client

    stdout = StringIO()
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
        environ={"EDGEFUL_API_KEY": "test-key"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "start date" in stderr.getvalue()
    assert created_clients == []


@pytest.mark.parametrize("date_arg", ["2026-99-99", "20260617"])
def test_run_reports_invalid_dates_to_injected_stderr_without_client_or_real_stderr(
    date_arg: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from edgeful_dash.cli import run

    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(api_key)
        created_clients.append(client)
        return client

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range", "--start-date", date_arg],
        environ={"EDGEFUL_API_KEY": "test-key"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert captured.err == ""
    assert "usage:" in stderr.getvalue()
    assert "edgeful-dash: error:" in stderr.getvalue()
    assert "YYYY-MM-DD" in stderr.getvalue()
    assert created_clients == []


def test_run_reports_expected_entitlement_error_without_traceback_or_key() -> None:
    from edgeful_dash.cli import run

    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(
            api_key,
            error=EntitlementError("Edgeful API denied access to this resource. code=EDGEFUL_FORBIDDEN"),
        )
        created_clients.append(client)
        return client

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range"],
        environ={"EDGEFUL_API_KEY": "top-secret"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
        today=date(2026, 6, 17),
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert (
        stderr.getvalue()
        == "Edgeful API denied access to this resource. code=EDGEFUL_FORBIDDEN\n"
    )
    assert "Traceback" not in stderr.getvalue()
    assert "top-secret" not in stderr.getvalue()
    assert len(created_clients) == 1
    assert created_clients[0].closed is True


def test_run_loads_environment_before_reading_mapping() -> None:
    from edgeful_dash.cli import run

    class MutableEnviron(dict[str, str]):
        pass

    environ = MutableEnviron()
    created_clients: list[FakeClient] = []

    def load_environment() -> None:
        environ["EDGEFUL_API_KEY"] = "loaded-later"

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(
            api_key,
            payload={
                "startDate": "2026-03-17",
                "endDate": "2026-06-16",
                "summary": {},
            },
        )
        created_clients.append(client)
        return client

    exit_code = run(
        ["previous-days-range"],
        environ=environ,
        load_environment=load_environment,
        client_factory=client_factory,
        stdout=StringIO(),
        stderr=StringIO(),
        today=date(2026, 6, 17),
    )

    assert exit_code == 0
    assert [client.api_key for client in created_clients] == ["loaded-later"]


def test_parser_and_main_do_not_expose_api_key_option(capsys: pytest.CaptureFixture[str]) -> None:
    from edgeful_dash.cli import build_parser, main

    parser = build_parser()
    help_text = parser.format_help()

    assert "api-key" not in help_text
    assert "EDGEFUL_API_KEY" not in help_text

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "api-key" not in captured.out
    assert "EDGEFUL_API_KEY" not in captured.out
