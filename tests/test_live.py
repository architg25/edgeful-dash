from __future__ import annotations

import pytest

from edgeful_dash.errors import ResponseFormatError
from edgeful_dash.live import (
    build_live_previous_days_range_request,
    summarize_live_previous_days_range,
)


def test_build_live_previous_days_range_request_normalizes_values() -> None:
    path, params = build_live_previous_days_range_request(
        ticker=" es ",
        market_type="FUTURES",
        session="ny",
        date_range="6MO",
    )

    assert path == "/live/futures/wip/report"
    assert params == {
        "ticker": "ES",
        "report_key": "previous_days_range_standard",
        "customization": "default",
        "session": "NY",
        "date_range": "6mo",
    }


@pytest.mark.parametrize("ticker", ["", "   ", "../ES", "..."])
def test_build_live_previous_days_range_request_rejects_invalid_ticker(
    ticker: str,
) -> None:
    with pytest.raises(ValueError, match="ticker"):
        build_live_previous_days_range_request(
            ticker=ticker,
            market_type="futures",
            session="NY",
            date_range="6mo",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("market_type", "crypto", "market type"),
        ("session", "TOKYO", "session"),
        ("date_range", "1y", "date range"),
    ],
)
def test_build_live_previous_days_range_request_rejects_unsupported_values(
    field: str,
    value: str,
    message: str,
) -> None:
    kwargs = {
        "ticker": "ES",
        "market_type": "futures",
        "session": "NY",
        "date_range": "6mo",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        build_live_previous_days_range_request(**kwargs)


def test_summarize_live_previous_days_range_formats_current_and_historical_data() -> None:
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
                "bias_break": "high",
                "context_value": "breakout",
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
                        },
                        {
                            "category": "high broken closed green",
                            "frequency": 49,
                            "percentage": 68,
                        },
                        {
                            "category": "high broken closed red",
                            "frequency": 23,
                            "percentage": 32,
                        },
                        {
                            "category": "previous day low broken",
                            "frequency": 59,
                            "percentage": 45,
                        },
                        {
                            "category": "low broken closed green",
                            "frequency": 23,
                            "percentage": 39,
                        },
                        {
                            "category": "low broken closed red",
                            "frequency": 36,
                            "percentage": 61,
                        },
                    ],
                },
            }
        },
    }

    lines = summarize_live_previous_days_range(payload, ticker="es")

    assert lines == [
        "Market status: market hours",
        "Ticker: ES",
        "Contract: ESU6",
        "As of: 2026-06-17T14:19:00",
        "Report status: in_play",
        "Touched previous high: yes",
        "Touched previous low: no",
        "Previous-day high: 7570.5",
        "Previous-day low: 7514.25",
        "Bias break: high",
        "Context: breakout",
        "Historical date range: 2025-12-17 to 2026-06-16",
        "Historical previous day high broken: count=72, percentage=55",
        "Historical high broken closed green: count=49, percentage=68",
        "Historical high broken closed red: count=23, percentage=32",
        "Historical previous day low broken: count=59, percentage=45",
        "Historical low broken closed green: count=23, percentage=39",
        "Historical low broken closed red: count=36, percentage=61",
    ]


def test_summarize_live_previous_days_range_requires_ticker_object() -> None:
    with pytest.raises(ResponseFormatError, match="ticker ES"):
        summarize_live_previous_days_range({}, ticker="ES")


def test_summarize_live_previous_days_range_requires_report_object() -> None:
    with pytest.raises(ResponseFormatError, match="previous-day range"):
        summarize_live_previous_days_range({"ES": {}}, ticker="ES")


def test_summarize_live_previous_days_range_omits_missing_optional_fields() -> None:
    payload = {
        "ES": {
            "previous_days_range_standard_default": {
                "touched_high": True,
            }
        }
    }

    lines = summarize_live_previous_days_range(payload, ticker="ES")

    assert lines == [
        "Ticker: ES",
        "Touched previous high: yes",
    ]
