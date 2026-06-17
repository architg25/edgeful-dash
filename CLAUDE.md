# edgeful-dash

Python CLI for Edgeful market data. Detailed guidance lives in `README.md`,
`docs/usage.md`, and `docs/development.md`.

## Get data

Use live data for requests containing current, today, live, or in-play:

```bash
uv run edgeful-dash live-previous-days-range \
  --ticker ES \
  --market-type futures
```

The live command reads one SSE event and saves nothing. Report Edgeful's exact
market status and as-of timestamp.

Use historical data for probabilities, comparisons, or date ranges:

```bash
mktemp -d
uv run edgeful-dash previous-days-range \
  --ticker ES \
  --market-type futures \
  --output-dir <returned-temp-directory>
```

The default range is 92 days ago through yesterday. Use `--start-date` and
`--end-date` only for a requested period. Delete temporary responses after
reading them and verify that `data/raw/` still contains only `.gitkeep`.

Defaults are futures, ticker `ES`, and the New York session. Ask when the
ticker, market, period, or session is materially ambiguous. Never fabricate
missing fields or silently change the meaning of Edgeful metrics.

## Build dashboards

The official Edgeful dashboard skill is installed at
`.claude/skills/dashboard/SKILL.md`. Use `/dashboard` when the user asks to
visualize, chart, or build a shareable dashboard. Fetch data with this project's
CLI first; the dashboard skill renders data but does not fetch it.

## Safety

- The API key is already in ignored `.env`; never print, copy, or commit it.
- Do not retain or commit API response JSON unless the user explicitly asks.
- Do not pass the API key on the command line.

## Development

Read the detailed docs before changing behavior. Verify changes with:

```bash
uv run pytest
git diff --check
```

Do not bypass tests or hooks. Do not create branches or worktrees unless asked.
