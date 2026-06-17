from __future__ import annotations

import re
from typing import Any

from edgeful_dash.errors import ResponseFormatError

LIVE_REPORT_KEY = "previous_days_range_standard"
LIVE_RESPONSE_KEY = "previous_days_range_standard_default"

_TICKER_PATTERN = re.compile(r"[A-Z0-9._-]+")
_MARKET_TYPES = {"futures", "stock"}
_SESSIONS = {"NY", "LONDON", "ASIA"}
_DATE_RANGES = {"3mo", "6mo"}


def build_live_previous_days_range_request(
    *,
    ticker: str,
    market_type: str,
    session: str,
    date_range: str,
) -> tuple[str, dict[str, str]]:
    normalized_ticker = _normalize_ticker(ticker)
    normalized_market_type = market_type.strip().lower()
    normalized_session = session.strip().upper()
    normalized_date_range = date_range.strip().lower()

    if normalized_market_type not in _MARKET_TYPES:
        raise ValueError("live market type must be futures or stock")
    if normalized_session not in _SESSIONS:
        raise ValueError("session must be NY, LONDON, or ASIA")
    if normalized_date_range not in _DATE_RANGES:
        raise ValueError("date range must be 3mo or 6mo")

    return (
        f"/live/{normalized_market_type}/wip/report",
        {
            "ticker": normalized_ticker,
            "report_key": LIVE_REPORT_KEY,
            "customization": "default",
            "session": normalized_session,
            "date_range": normalized_date_range,
        },
    )


def summarize_live_previous_days_range(
    payload: dict[str, Any],
    *,
    ticker: str,
) -> list[str]:
    normalized_ticker = _normalize_ticker(ticker)
    ticker_payload = payload.get(normalized_ticker)
    if not isinstance(ticker_payload, dict):
        raise ResponseFormatError(
            f"Edgeful live response did not contain ticker {normalized_ticker}."
        )

    report = ticker_payload.get(LIVE_RESPONSE_KEY)
    if not isinstance(report, dict):
        raise ResponseFormatError(
            "Edgeful live response did not contain the previous-day range report."
        )

    lines: list[str] = []
    _append_string(lines, "Market status", payload.get("market_status"))
    lines.append(f"Ticker: {normalized_ticker}")

    contracts = payload.get("futures_contracts")
    if isinstance(contracts, dict):
        contract = contracts.get(normalized_ticker)
        if isinstance(contract, dict):
            _append_string(lines, "Contract", contract.get("contract"))
            _append_string(lines, "As of", contract.get("as_of"))

    _append_string(lines, "Report status", report.get("report_status"))
    _append_boolean(lines, "Touched previous high", report.get("touched_high"))
    _append_boolean(lines, "Touched previous low", report.get("touched_low"))
    _append_scalar(lines, "Previous-day high", report.get("previous_high"))
    _append_scalar(lines, "Previous-day low", report.get("previous_low"))
    _append_string(lines, "Bias break", report.get("bias_break"))
    _append_string(lines, "Context", report.get("context_value"))

    historical = report.get("historical")
    if isinstance(historical, dict):
        start_date = historical.get("startDate")
        end_date = historical.get("endDate")
        if isinstance(start_date, str) and isinstance(end_date, str):
            lines.append(f"Historical date range: {start_date} to {end_date}")
        _append_historical_summary(lines, historical.get("summary"))

    return lines


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper().replace("/", "")
    if not normalized:
        raise ValueError("ticker must not be blank")
    if (
        not _TICKER_PATTERN.fullmatch(normalized)
        or normalized.strip(".") == ""
        or ".." in normalized
    ):
        raise ValueError("ticker contains unsafe characters")
    return normalized


def _append_string(lines: list[str], label: str, value: Any) -> None:
    if isinstance(value, str) and value:
        lines.append(f"{label}: {value}")


def _append_boolean(lines: list[str], label: str, value: Any) -> None:
    if isinstance(value, bool):
        lines.append(f"{label}: {'yes' if value else 'no'}")


def _append_scalar(lines: list[str], label: str, value: Any) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        lines.append(f"{label}: {value}")


def _append_historical_summary(lines: list[str], summary: Any) -> None:
    if not isinstance(summary, list):
        return

    for item in summary:
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        if not isinstance(category, str) or not category:
            continue

        parts: list[str] = []
        if "frequency" in item:
            parts.append(f"count={item['frequency']}")
        if "percentage" in item:
            parts.append(f"percentage={item['percentage']}")
        if parts:
            lines.append(f"Historical {category}: {', '.join(parts)}")
