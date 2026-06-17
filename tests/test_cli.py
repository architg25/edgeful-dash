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
        self.sse_calls: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def get(self, path: str, params: dict[str, str]) -> dict:
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error
        return self.payload

    def get_sse_event(self, path: str, params: dict[str, str]) -> dict:
        self.sse_calls.append((path, params))
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


def test_previous_days_range_parser_defaults_to_saving() -> None:
    from edgeful_dash.cli import build_parser

    args = build_parser().parse_args(["previous-days-range"])

    assert args.no_save is False


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


def test_run_historical_no_save_prints_summary_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.chdir(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["previous-days-range", "--no-save"],
        environ={"EDGEFUL_API_KEY": "fake-secret-key"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
        today=date(2026, 6, 17),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert created_clients[0].closed is True
    assert "Previous-day high: count=31, percentage=52.5" in stdout.getvalue()
    assert "Previous-day low: count=28, percentage=47.5" in stdout.getvalue()
    assert "Saved response:" not in stdout.getvalue()
    assert list(tmp_path.iterdir()) == []


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


def test_live_previous_days_range_parser_defaults() -> None:
    from edgeful_dash.cli import build_parser

    args = build_parser().parse_args(["live-previous-days-range"])

    assert args.ticker == "ES"
    assert args.market_type == "futures"
    assert args.session == "NY"
    assert args.date_range == "6mo"


def test_run_executes_live_previous_days_range_without_saving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from edgeful_dash.cli import run

    payload = {
        "market_status": "market hours",
        "futures_contracts": {
            "ES": {
                "contract": "ESU6",
                "as_of": "2026-06-17T14:19:00",
            }
        },
        "ES": {
            "previous_days_range_standard_default": {
                "touched_high": True,
                "touched_low": False,
                "previous_high": 7570.5,
                "previous_low": 7514.25,
                "report_status": "in_play",
                "historical": {
                    "startDate": "2025-12-17",
                    "endDate": "2026-06-16",
                    "summary": [
                        {
                            "category": "previous day high broken",
                            "frequency": 72,
                            "percentage": 55,
                        }
                    ],
                },
            }
        },
    }
    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(api_key, payload=payload)
        created_clients.append(client)
        return client

    monkeypatch.chdir(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["live-previous-days-range"],
        environ={"EDGEFUL_API_KEY": "fake-secret-key"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert len(created_clients) == 1
    client = created_clients[0]
    assert client.calls == []
    assert client.sse_calls == [
        (
            "/live/futures/wip/report",
            {
                "ticker": "ES",
                "report_key": "previous_days_range_standard",
                "customization": "default",
                "session": "NY",
                "date_range": "6mo",
            },
        )
    ]
    assert client.closed is True

    output = stdout.getvalue()
    assert "Market status: market hours" in output
    assert "Ticker: ES" in output
    assert "Contract: ESU6" in output
    assert "Touched previous high: yes" in output
    assert "Historical previous day high broken: count=72, percentage=55" in output
    assert "Saved response:" not in output
    assert "fake-secret-key" not in output
    assert list(tmp_path.iterdir()) == []


def test_run_reports_live_entitlement_error_and_closes_client() -> None:
    from edgeful_dash.cli import run

    created_clients: list[FakeClient] = []

    def client_factory(api_key: str) -> FakeClient:
        client = FakeClient(
            api_key,
            error=EntitlementError(
                "Edgeful API denied access to this resource. code=live_data_not_allowed"
            ),
        )
        created_clients.append(client)
        return client

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run(
        ["live-previous-days-range", "--ticker", "NQ"],
        environ={"EDGEFUL_API_KEY": "top-secret"},
        load_environment=lambda: None,
        client_factory=client_factory,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "live_data_not_allowed" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()
    assert "top-secret" not in stderr.getvalue()
    assert len(created_clients) == 1
    assert created_clients[0].closed is True
