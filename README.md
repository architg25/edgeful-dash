# edgeful-dash

`edgeful-dash` is a small Python CLI for requesting Edgeful report data. It supports both a one-shot current previous-day range snapshot and historical previous-day range statistics.

## Quick start

You need Python 3.12 or newer, [`uv`](https://docs.astral.sh/uv/), and an Edgeful API key.

```bash
uv sync --dev
cp .env.example .env
```

Set the key in `.env`:

```dotenv
EDGEFUL_API_KEY=ef_live_your_key_here
```

Get the current ES previous-day range state:

```bash
uv run edgeful-dash live-previous-days-range --ticker ES
```

This consumes the first current event from Edgeful's live stream, prints a concise summary, and saves no response file. Live API access requires Edgeful Pro or All-Access.

For historical NQ statistics:

```bash
uv run edgeful-dash previous-days-range \
  --ticker NQ \
  --market-type futures \
  --start-date 2026-03-17 \
  --end-date 2026-06-16
```

Omit historical dates to use the default rolling window: 92 days before today through yesterday.

## What it produces

The live command prints current market status, contract/as-of metadata, previous-high/low state, and attached historical context without writing a file.

The historical command prints aggregate metrics and saves the complete JSON object to a deterministic path such as:

```text
data/raw/previous-days-range_futures_NQ_2026-03-17_2026-06-16.json
```

Files generated under `data/raw/` are ignored by git.

## Documentation

- [CLI usage and troubleshooting](docs/usage.md)
- [Development and architecture](docs/development.md)
- [Edgeful API overview](https://help.edgeful.com/en/articles/15182638-the-edgeful-api-overview-walkthrough)

## Security

Never commit `.env`, API keys, or real API responses. The repository ignores `.env` and generated files under `data/raw/`, but you should still check `git status` before committing.
