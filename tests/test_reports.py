from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from edgeful_dash.reports import (
    build_previous_days_range_request,
    default_date_range,
    save_response,
    summarize_previous_days_range,
)


def test_default_date_range_uses_completed_days() -> None:
    assert default_date_range(date(2026, 6, 17)) == (
        date(2026, 3, 17),
        date(2026, 6, 16),
    )


def test_build_previous_days_range_request_returns_documented_path_and_params() -> None:
    path, params = build_previous_days_range_request(
        ticker="rty",
        market_type="futures",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
        start_time="09:30:00",
        end_time="16:00:00",
        timezone="America/New_York",
    )

    assert path == "/report_calculation/previous-days-range-standard/futures/RTY"
    assert params == {
        "start_date": "2026-03-17",
        "end_date": "2026-06-16",
        "start_time": "09:30:00",
        "end_time": "16:00:00",
        "timezone": "America/New_York",
    }


def test_build_previous_days_range_request_rejects_reversed_dates() -> None:
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


def test_build_previous_days_range_request_rejects_blank_ticker() -> None:
    with pytest.raises(ValueError, match="ticker"):
        build_previous_days_range_request(
            ticker="   ",
            market_type="futures",
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


def test_build_previous_days_range_request_rejects_blank_market_type() -> None:
    with pytest.raises(ValueError, match="market type"):
        build_previous_days_range_request(
            ticker="RTY",
            market_type="   ",
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


@pytest.mark.parametrize("ticker", ["RTY?", "RTY#1"])
def test_build_previous_days_range_request_rejects_unsafe_ticker_path_segments(
    ticker: str,
) -> None:
    with pytest.raises(ValueError, match="ticker"):
        build_previous_days_range_request(
            ticker=ticker,
            market_type="futures",
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


@pytest.mark.parametrize("ticker", [".", ".."])
def test_build_previous_days_range_request_rejects_all_dot_tickers(
    ticker: str,
) -> None:
    with pytest.raises(ValueError, match="ticker"):
        build_previous_days_range_request(
            ticker=ticker,
            market_type="futures",
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


@pytest.mark.parametrize("market_type", ["fut/ures", "..", "futures?", "futures#x"])
def test_build_previous_days_range_request_rejects_unsafe_market_type_path_segments(
    market_type: str,
) -> None:
    with pytest.raises(ValueError, match="market type"):
        build_previous_days_range_request(
            ticker="RTY",
            market_type=market_type,
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


def test_build_previous_days_range_request_rejects_ticker_that_becomes_blank_after_slash_removal() -> None:
    with pytest.raises(ValueError, match="ticker"):
        build_previous_days_range_request(
            ticker="/",
            market_type="futures",
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
            start_time="09:30:00",
            end_time="16:00:00",
            timezone="America/New_York",
        )


def test_build_previous_days_range_request_preserves_documented_slash_normalization() -> None:
    path, _ = build_previous_days_range_request(
        ticker="ETH/USDT",
        market_type="crypto-perp",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
        start_time="09:30:00",
        end_time="16:00:00",
        timezone="America/New_York",
    )

    assert path == "/report_calculation/previous-days-range-standard/crypto-perp/ETHUSDT"


def test_summarize_previous_days_range_omits_absent_optional_fields() -> None:
    payload = {
        "startDate": "2026-03-17",
        "endDate": "2026-06-16",
        "summary": {
            "prevDayHigh": {"count": 31, "percentage": 52.5},
            "prevDayLow": {"count": 28},
            "prevDayHighGreen": "20 of 31",
        },
    }

    assert summarize_previous_days_range(payload) == [
        "Date range: 2026-03-17 to 2026-06-16",
        "Previous-day high: count=31, percentage=52.5",
        "Previous-day low: count=28",
        "Previous-day high, green close: 20 of 31",
    ]


def test_save_response_creates_directory_and_preserves_payload(
    tmp_path: Path,
) -> None:
    payload = {
        "summary": {
            "prevDayHigh": {"count": 1, "percentage": 50.0},
            "prevDayLowRed": {"count": 1},
        }
    }
    output_dir = tmp_path / "nested" / "reports"

    path = save_response(
        payload,
        output_dir=output_dir,
        market_type="FUTURES",
        ticker="RTY",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
    )

    assert path == output_dir / "previous-days-range_futures_RTY_2026-03-17_2026-06-16.json"
    assert path.parent.is_dir()
    assert path.read_text() == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert json.loads(path.read_text()) == payload


@pytest.mark.parametrize(
    ("ticker", "market_type"),
    [
        ("RTY?x=1", "futures"),
        ("RTY", "../futures"),
    ],
)
def test_save_response_rejects_unsafe_filename_segments_without_writing_files(
    tmp_path: Path,
    ticker: str,
    market_type: str,
) -> None:
    output_dir = tmp_path / "safe-output"
    payload = {"summary": {"prevDayHigh": {"count": 1}}}

    with pytest.raises(ValueError, match="ticker|market type"):
        save_response(
            payload,
            output_dir=output_dir,
            market_type=market_type,
            ticker=ticker,
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
        )

    assert list(tmp_path.rglob("*.json")) == []


@pytest.mark.parametrize("ticker", [".", ".."])
def test_save_response_rejects_all_dot_tickers_without_writing_files(
    tmp_path: Path,
    ticker: str,
) -> None:
    output_dir = tmp_path / "safe-output"

    with pytest.raises(ValueError, match="ticker"):
        save_response(
            {"summary": {}},
            output_dir=output_dir,
            market_type="futures",
            ticker=ticker,
            start_date=date(2026, 3, 17),
            end_date=date(2026, 6, 16),
        )

    assert list(tmp_path.rglob("*.json")) == []


def test_save_response_preserves_documented_slash_normalization(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "reports"

    path = save_response(
        {"summary": {}},
        output_dir=output_dir,
        market_type="crypto-perp",
        ticker="ETH/USDT",
        start_date=date(2026, 3, 17),
        end_date=date(2026, 6, 16),
    )

    assert path.name == "previous-days-range_crypto-perp_ETH-USDT_2026-03-17_2026-06-16.json"
