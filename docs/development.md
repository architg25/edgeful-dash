# Development

## Local setup

The project targets Python 3.12 or newer and uses `uv` for dependency management.

```bash
uv sync --dev
uv run pytest
```

Tests do not make live Edgeful requests. HTTP behavior is exercised with in-memory transports and injected clients.

## Project structure

```text
src/edgeful_dash/
├── cli.py       # Argument parsing, environment loading, and command orchestration
├── client.py    # JSON/SSE transport, authentication, status mapping, and retries
├── errors.py    # User-facing exception hierarchy
├── live.py      # Live request construction and current-event summaries
└── reports.py   # Report request construction, summaries, and JSON persistence
```

The boundaries are deliberately boring:

- `cli.py` owns process concerns: arguments, streams, exit codes, and dependency wiring.
- `client.py` owns generic Edgeful HTTP behavior, including first-event SSE parsing, and must not know how a specific report is summarized.
- `live.py` owns current previous-day range request parameters and summary formatting.
- `reports.py` owns report-specific paths, parameters, normalization, presentation, and filenames.
- `errors.py` gives the CLI a stable set of expected failures to catch.

Do not turn the client into a generic speculative SDK. Add the report behavior the application actually uses.

## Request flow

1. `cli.run()` parses the command and loads `.env`.
2. The CLI reads `EDGEFUL_API_KEY` without printing it.
3. The report module validates and normalizes request values.
4. `EdgefulClient.get()` retrieves historical JSON, or `get_sse_event()` reads the first live SSE event.
5. Historical commands save the complete JSON object by default and skip persistence with `--no-save`; live commands do not persist the event.
6. The relevant report module formats fields that are actually present.
7. The CLI prints the summary, or a concise expected error.

The client owns an internally created `httpx.Client` and closes it after the request. Tests can inject a client and a sleep function to avoid network calls and real retry delays.

## Tests

```text
tests/
├── test_cli.py       # Argument handling, orchestration, output, and exit codes
├── test_client.py    # Authentication, status mapping, redaction, parsing, and retries
├── test_live.py      # Live request validation and current-event summaries
└── test_reports.py   # Dates, normalization, request shape, summaries, and persistence
```

Run everything:

```bash
uv run pytest
```

GitHub Actions runs the same suite and CLI help smoke checks on
`windows-latest` and `ubuntu-latest`. CI does not use an Edgeful API key.

Run one module while developing:

```bash
uv run pytest tests/test_reports.py
```

Any change to request construction, retry behavior, filenames, or CLI output needs a focused test before the implementation change.

## Credentials and response data

- Never read, print, fixture, or commit the local `.env` file.
- Use `.env.example` for configuration documentation.
- Keep real Edgeful responses under ignored `data/raw/`.
- Use small synthetic payloads in tests. Real responses are account-specific and can become stale or expose paid data.
- Check `git status` before every commit. An ignore rule is protection against mistakes, not permission to stop looking.

## Adding another report

Keep transport and report behavior separate:

1. Add request construction and summary functions to `reports.py`, or create a focused report module if that file would become unwieldy.
2. Add unit tests for validation, endpoint path, query parameters, summary fields, and output filename.
3. Add a CLI subcommand that calls those functions through `EdgefulClient`.
4. Add CLI tests with an injected fake client. Do not use a live API key in tests.
5. Run the focused tests, then the full suite.
6. Update `README.md` only if the quick-start command changes; put the complete command reference in `docs/usage.md`.

If a report needs transport behavior that is not generic to all requests, keep it out of `EdgefulClient`.

## Verification

Before committing:

```bash
uv run pytest
uv run edgeful-dash --help
uv run edgeful-dash live-previous-days-range --help
uv run edgeful-dash previous-days-range --help
git diff --check
git status --short
```

For credential and response exclusions:

```bash
git check-ignore -v .env data/raw/*.json
```

Do not bypass test failures or commit hooks. If a live smoke test is needed, run it manually with the ignored `.env` file and inspect only the non-secret summary output.
