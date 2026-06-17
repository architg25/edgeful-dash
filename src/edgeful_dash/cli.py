from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

from edgeful_dash.client import EdgefulClient
from edgeful_dash.errors import EdgefulError
from edgeful_dash.live import (
    build_live_previous_days_range_request,
    summarize_live_previous_days_range,
)
from edgeful_dash.reports import (
    build_previous_days_range_request,
    default_date_range,
    save_response,
    summarize_previous_days_range,
)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class _ParseError(Exception):
    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ParseError(self, message)


def _strict_date(value: str) -> date:
    if _DATE_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("expected date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected date in YYYY-MM-DD format") from error


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="edgeful-dash")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)
    previous_days_range = subparsers.add_parser("previous-days-range")
    previous_days_range.add_argument("--ticker", default="RTY")
    previous_days_range.add_argument("--market-type", default="futures")
    previous_days_range.add_argument("--start-date", type=_strict_date)
    previous_days_range.add_argument("--end-date", type=_strict_date)
    previous_days_range.add_argument("--start-time", default="09:30:00")
    previous_days_range.add_argument("--end-time", default="16:00:00")
    previous_days_range.add_argument("--timezone", default="America/New_York")
    previous_days_range.add_argument("--output-dir", type=Path, default=Path("data/raw"))

    live_previous_days_range = subparsers.add_parser("live-previous-days-range")
    live_previous_days_range.add_argument("--ticker", default="ES")
    live_previous_days_range.add_argument(
        "--market-type",
        choices=("futures", "stock"),
        default="futures",
    )
    live_previous_days_range.add_argument(
        "--session",
        choices=("NY", "LONDON", "ASIA"),
        default="NY",
    )
    live_previous_days_range.add_argument(
        "--date-range",
        choices=("3mo", "6mo"),
        default="6mo",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    load_environment: Callable[[], bool] | Callable[[], None] = load_dotenv,
    client_factory: type[EdgefulClient] | Callable[[str], EdgefulClient] = EdgefulClient,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    today: date | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except _ParseError as error:
        error.parser.print_usage(stderr)
        print(f"edgeful-dash: error: {error.message}", file=stderr)
        return 2
    load_environment()

    api_key = environ.get("EDGEFUL_API_KEY", "").strip()
    if not api_key:
        print(
            "EDGEFUL_API_KEY is required. Set it in your environment or local .env file.",
            file=stderr,
        )
        return 2

    try:
        is_live = args.command == "live-previous-days-range"
        if is_live:
            path, params = build_live_previous_days_range_request(
                ticker=args.ticker,
                market_type=args.market_type,
                session=args.session,
                date_range=args.date_range,
            )
        else:
            start_date, end_date = default_date_range(today)
            if args.start_date is not None:
                start_date = args.start_date
            if args.end_date is not None:
                end_date = args.end_date
            path, params = build_previous_days_range_request(
                ticker=args.ticker,
                market_type=args.market_type,
                start_date=start_date,
                end_date=end_date,
                start_time=args.start_time,
                end_time=args.end_time,
                timezone=args.timezone,
            )

        client = client_factory(api_key)
        try:
            if is_live:
                payload = client.get_sse_event(path, params)
            else:
                payload = client.get(path, params)
        finally:
            client.close()

        if is_live:
            summary_lines = summarize_live_previous_days_range(
                payload,
                ticker=args.ticker,
            )
        else:
            saved_path = save_response(
                payload,
                output_dir=args.output_dir,
                market_type=args.market_type,
                ticker=args.ticker,
                start_date=start_date,
                end_date=end_date,
            )
            summary_lines = summarize_previous_days_range(payload)

        for line in summary_lines:
            print(line, file=stdout)
        if not is_live:
            print(f"Saved response: {saved_path}", file=stdout)
    except (EdgefulError, OSError, ValueError) as error:
        print(str(error), file=stderr)
        return 2

    return 0


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(run(argv))
