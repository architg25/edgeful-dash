from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REQUEST_TICKER_PATTERN = re.compile(r"[A-Z0-9._-]+")
_FILENAME_TICKER_PATTERN = re.compile(r"[A-Z0-9._-]+")
_MARKET_TYPE_PATTERN = re.compile(r"[a-z0-9-]+")


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

    normalized_ticker = _normalize_request_ticker(ticker)
    normalized_market_type = _normalize_market_type(market_type)

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
    lines: list[str] = []
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

    parts: list[str] = []
    if "count" in value:
        parts.append(f"count={value['count']}")
    if "percentage" in value:
        parts.append(f"percentage={value['percentage']}")

    if not parts:
        return f"{label}: {value}"
    return f"{label}: {', '.join(parts)}"


def _normalize_request_ticker(ticker: str) -> str:
    normalized_ticker = ticker.strip().upper().replace("/", "")
    return _require_ticker(
        normalized_ticker,
        pattern=_REQUEST_TICKER_PATTERN,
        blank_message="ticker must not be blank",
        invalid_message="ticker contains unsafe characters",
    )


def _normalize_filename_ticker(ticker: str) -> str:
    normalized_ticker = ticker.strip().upper().replace("/", "-")
    return _require_ticker(
        normalized_ticker,
        pattern=_FILENAME_TICKER_PATTERN,
        blank_message="ticker must not be blank",
        invalid_message="ticker contains unsafe characters",
    )


def _normalize_market_type(market_type: str) -> str:
    normalized_market_type = market_type.strip().lower()
    return _require_match(
        normalized_market_type,
        pattern=_MARKET_TYPE_PATTERN,
        blank_message="market type must not be blank",
        invalid_message="market type contains unsafe characters",
    )


def _require_match(
    value: str,
    *,
    pattern: re.Pattern[str],
    blank_message: str,
    invalid_message: str,
) -> str:
    if not value:
        raise ValueError(blank_message)
    if not pattern.fullmatch(value):
        raise ValueError(invalid_message)
    return value


def _require_ticker(
    value: str,
    *,
    pattern: re.Pattern[str],
    blank_message: str,
    invalid_message: str,
) -> str:
    normalized_value = _require_match(
        value,
        pattern=pattern,
        blank_message=blank_message,
        invalid_message=invalid_message,
    )
    if normalized_value.strip(".") == "":
        raise ValueError(invalid_message)
    return normalized_value


def save_response(
    payload: dict[str, Any],
    *,
    output_dir: Path,
    market_type: str,
    ticker: str,
    start_date: date,
    end_date: date,
) -> Path:
    safe_market_type = _normalize_market_type(market_type)
    safe_ticker = _normalize_filename_ticker(ticker)
    filename = (
        "previous-days-range_"
        f"{safe_market_type}_{safe_ticker}_"
        f"{start_date.isoformat()}_{end_date.isoformat()}.json"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path
