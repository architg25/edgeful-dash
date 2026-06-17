# edgeful-dash

`edgeful-dash` is a small Python CLI for requesting Edgeful report data, printing a useful summary, and saving the complete JSON response for later analysis. It currently supports Edgeful's previous-day range report.

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

Then request the NQ futures report:

```bash
uv run edgeful-dash previous-days-range \
  --ticker NQ \
  --market-type futures \
  --start-date 2026-03-17 \
  --end-date 2026-06-16
```

Omit the dates to use the default rolling window: 92 days before today through yesterday.

## What it produces

The command prints the report's available headline metrics and saves the complete JSON object to a deterministic path such as:

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
