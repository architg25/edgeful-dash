# edgeful-dash

Small Python CLI for fetching Edgeful report data and saving the complete JSON response.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Edgeful API key from the [Edgeful API dashboard](https://www.edgeful.com/api-dashboard)

## Setup

```bash
uv sync --dev
cp .env.example .env
```

Open `.env` and paste your key after `EDGEFUL_API_KEY=`:

```dotenv
EDGEFUL_API_KEY=ef_live_your_key_here
```

Edgeful shows the plaintext key once. Do not commit `.env` or paste the key into chat, shell history, screenshots, or logs.

## Usage

Default command:

```bash
uv run edgeful-dash previous-days-range
```

Defaults:

- previous day's range
- `RTY` futures
- prior 92 completed days
- `09:30:00` to `16:00:00` in `America/New_York`
- responses saved under `data/raw/`

Full override example:

```bash
uv run edgeful-dash previous-days-range \
  --ticker ETHUSDT \
  --market-type crypto-perp \
  --start-date 2026-03-17 \
  --end-date 2026-06-16 \
  --start-time 00:00:00 \
  --end-time 23:59:59 \
  --timezone UTC \
  --output-dir tmp/edgeful
```

Expected errors are concise and do not print Python tracebacks. Generated JSON files under `data/raw/` are ignored by git.

## Tests

```bash
uv run pytest
```

Tests use in-memory HTTP transport and injected clients, so they do not make live Edgeful API calls.

## API Notes

- Base URL: `https://api.edgeful.com`
- Authentication: `Authorization: Bearer <EDGEFUL_API_KEY>`
- `401`: bad or missing API key
- `403`: authenticated but not entitled to that resource
- `429`: rate limited after bounded retries

Current documented limits: 30 requests per 60 seconds, 5 requests per 5 seconds, and 500 requests per hour. Plan entitlements control which reports, tickers, history depth, live access, and detail levels Edgeful returns.
