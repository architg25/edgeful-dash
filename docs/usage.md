# CLI usage

## Setup

Install dependencies and create the local environment file:

```bash
uv sync --dev
cp .env.example .env
```

Add your Edgeful API key to `.env`:

```dotenv
EDGEFUL_API_KEY=ef_live_your_key_here
```

The CLI also accepts `EDGEFUL_API_KEY` from the process environment. Do not pass the key as a command-line argument because shell history and process listings can expose it.

## Previous-day range report

```bash
uv run edgeful-dash previous-days-range [options]
```

The command requests:

```text
GET /report_calculation/previous-days-range-standard/{market_type}/{ticker}
```

It sends the date range, session times, and timezone as query parameters.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `--ticker` | `RTY` | Instrument ticker. Input is trimmed, uppercased, and `/` is removed for the API request. |
| `--market-type` | `futures` | Edgeful market type. Supported API values are `stock`, `futures`, `forex`, and `crypto`. |
| `--start-date` | 92 days before today | First report date, strictly formatted as `YYYY-MM-DD`. |
| `--end-date` | Yesterday | Last report date, strictly formatted as `YYYY-MM-DD`. |
| `--start-time` | `09:30:00` | Session start time sent to Edgeful. |
| `--end-time` | `16:00:00` | Session end time sent to Edgeful. |
| `--timezone` | `America/New_York` | IANA timezone used for the session. |
| `--output-dir` | `data/raw` | Directory for the complete JSON response. |

The start date cannot be after the end date. The CLI validates date formatting locally; Edgeful validates ticker availability, market access, history depth, and session support.

## Examples

NQ futures during the regular New York session:

```bash
uv run edgeful-dash previous-days-range \
  --ticker NQ \
  --market-type futures \
  --start-date 2026-03-17 \
  --end-date 2026-06-16
```

A stock:

```bash
uv run edgeful-dash previous-days-range \
  --ticker AAPL \
  --market-type stock \
  --start-date 2026-05-01 \
  --end-date 2026-05-30
```

A forex pair using the New York forex session:

```bash
uv run edgeful-dash previous-days-range \
  --ticker EUR/USD \
  --market-type forex \
  --start-date 2026-05-01 \
  --end-date 2026-05-30 \
  --start-time 08:00:00 \
  --end-time 17:00:00 \
  --timezone America/New_York
```

A crypto instrument:

```bash
uv run edgeful-dash previous-days-range \
  --ticker BTCUSDT \
  --market-type crypto \
  --start-date 2026-05-01 \
  --end-date 2026-05-30 \
  --start-time 09:30:00 \
  --end-time 16:00:00 \
  --timezone America/New_York
```

These examples show valid request syntax. Whether a ticker and date range return data depends on the Edgeful plan and available history.

## Session behavior

- Futures commonly use `09:30:00` through `16:00:00` in `America/New_York`.
- The documented New York forex session is `08:00:00` through `17:00:00`.
- Edgeful documents a New York crypto session of `09:30:00` through `16:00:00`.
- For stocks, Edgeful uses the market's standard session and ignores custom intraday session values for this report.

Session values are sent directly to Edgeful. The CLI does not attempt to interpret holidays, daylight-saving changes, or exchange calendars.

## Output

When present in the response, the CLI prints:

- requested date range;
- previous-day high and low counts and percentages;
- green/red close breakdowns after high or low breaks;
- the path of the saved response.

The saved filename is:

```text
previous-days-range_{market_type}_{ticker}_{start_date}_{end_date}.json
```

For example:

```text
data/raw/previous-days-range_futures_NQ_2026-03-17_2026-06-16.json
```

The response is formatted as readable JSON without dropping fields. Generated files under `data/raw/` are ignored by git.

## Errors

Expected failures are printed without a Python traceback, and the command exits with status `2`.

| Failure | Meaning |
| --- | --- |
| Missing `EDGEFUL_API_KEY` | The environment variable is absent or blank. |
| HTTP `401` | Edgeful rejected the API key. |
| HTTP `403` | The key is valid but the account is not entitled to the requested resource. |
| HTTP `404` | The ticker, market type, report, or requested historical data is unavailable. |
| HTTP `429` | Edgeful is rate limiting requests. |
| Network failure | No response was received from Edgeful. |
| Invalid JSON or non-object JSON | Edgeful returned a response shape the client cannot process. |

Only HTTP `429` responses are retried. The client makes at most three attempts, waiting one second before the second attempt and two seconds before the third. Other failures return immediately.

Edgeful's published limits are:

- 30 requests per 60 seconds;
- 5 requests per 5 seconds;
- 500 requests per hour.

Account entitlements may impose additional restrictions on reports, tickers, history depth, live data, and detail level.

## Command help

```bash
uv run edgeful-dash --help
uv run edgeful-dash previous-days-range --help
```
