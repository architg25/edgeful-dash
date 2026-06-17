# Edgeful CLI Design

## Goal

Create a small, reliable command-line client that proves authenticated access to
the Edgeful API, fetches an Essentials-compatible report, prints the useful
headline values, and preserves the complete response as JSON for later analysis
or dashboard work.

The first live request will fetch the RTY previous-day's-range report for the
New York session over the previous 92 completed calendar days.

## Scope

The first version includes:

- a standalone Python 3.12 project managed with `uv`;
- local API-key storage through an ignored `.env` file;
- an Edgeful HTTP client with bounded rate-limit retries;
- one CLI command for the previous-day's-range report;
- configurable ticker, market type, date range, and session values;
- concise terminal output derived only from fields present in the response;
- storage of the unmodified JSON response under `data/raw/`;
- unit tests and an opt-in live smoke test.

The first version does not include:

- a browser UI;
- charts or generated HTML;
- scheduled jobs;
- a generic wrapper for every Edgeful endpoint;
- installation of Edgeful's optional dashboard skill.

Those features can be added after the API boundary is verified. Building them
now would mix API discovery with presentation work and make failures harder to
isolate.

## Technology Choice

Use Python 3.12 with:

- `httpx` for HTTP requests;
- `python-dotenv` for local environment loading;
- the standard-library `argparse` module for the CLI;
- `pytest` for tests;
- `uv` for dependency and command management.

`argparse` avoids adding a CLI framework for one command. `httpx` provides
clean status handling and dependency injection for tests without requiring
network calls.

## Repository Structure

```text
edgeful-dash/
├── .env
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── data/
│   └── raw/
│       └── .gitkeep
├── docs/
│   └── superpowers/
│       ├── plans/
│       └── specs/
├── src/
│   └── edgeful_dash/
│       ├── __init__.py
│       ├── cli.py
│       ├── client.py
│       ├── errors.py
│       └── reports.py
└── tests/
    ├── test_cli.py
    ├── test_client.py
    └── test_reports.py
```

Each module has one responsibility:

- `client.py` owns authenticated HTTP transport and retries.
- `errors.py` defines actionable API exceptions.
- `reports.py` owns endpoint paths, parameters, response summarization, and
  output filenames for the supported report.
- `cli.py` parses user input and coordinates the other modules.

## Configuration and Credential Handling

The API key is read only from `EDGEFUL_API_KEY`.

The repository contains:

- `.env` with an empty `EDGEFUL_API_KEY=` placeholder;
- `.env.example` with the same placeholder;
- `.gitignore` entries for `.env`, Python build artifacts, virtual
  environments, test caches, and generated report JSON.

The CLI must not:

- accept the key as a command-line argument;
- print or log the full key;
- include the key in exception messages;
- write the key into report output.

Startup fails before making a request when the variable is missing or blank.
The error tells the user to populate `.env` without echoing its contents.

## API Client

The base URL is `https://api.edgeful.com`. Requests send:

```text
Authorization: Bearer <EDGEFUL_API_KEY>
Accept: application/json
```

The transport accepts an injected `httpx.Client`, allowing unit tests to use
`httpx.MockTransport` and exercise real request construction without accessing
the network.

The client maps responses as follows:

- `200`: decode and return a JSON object;
- `401`: raise an authentication error explaining that the key is missing,
  malformed, revoked, or not loaded;
- `403`: raise an entitlement error and preserve Edgeful's non-secret response
  code or message when present;
- `429`: retry with exponential delays of 1 and 2 seconds, for at most three
  total attempts, then raise a rate-limit error;
- other `4xx` or `5xx`: raise a general API error containing the status and a
  bounded, non-secret response message;
- invalid JSON: raise a response-format error.

Retries apply only to `429` responses. Authentication, entitlement, invalid
parameters, and server failures are not blindly retried.

## Report Command

The initial CLI interface is:

```bash
uv run edgeful-dash previous-days-range
```

Defaults:

- ticker: `RTY`;
- market type: `futures`;
- start date: today minus 92 days;
- end date: yesterday;
- session start: `09:30:00`;
- session end: `16:00:00`;
- timezone: `America/New_York`;
- output directory: `data/raw`.

Supported overrides:

```text
--ticker
--market-type
--start-date
--end-date
--start-time
--end-time
--timezone
--output-dir
```

Dates must use `YYYY-MM-DD`. The start date must not be after the end date.
The command calls:

```text
/report_calculation/previous-days-range-standard/{market_type}/{ticker}
```

with the documented date and session query parameters.

The initial implementation supports this endpoint deliberately rather than
pretending to offer a generic report abstraction before the response shapes
are understood.

## Output

On success, the CLI prints:

- the returned start and end dates when present;
- `summary.prevDayHigh` count and percentage when present;
- `summary.prevDayLow` count and percentage when present;
- the optional green/red breakdowns when present;
- the path of the saved JSON file.

The summarizer never invents sample sizes, inside-range counts, or alternate
field names. Missing optional values are omitted.

The complete response is saved without transformation using a deterministic
filename containing the report name, market type, ticker, start date, and end
date. Existing files are replaced only when the same request is deliberately
run again.

## Failure Behavior

CLI failures produce a concise message on standard error and a non-zero exit
status. They do not emit Python tracebacks for expected configuration or API
errors.

Invalid local arguments fail before network access. API failures retain enough
context to distinguish credentials, plan restrictions, rate limits, and
unexpected service responses.

Partial or unfamiliar successful response objects are still saved. The
terminal summary includes only recognized fields that are actually present.

## Testing

Tests use `httpx.MockTransport`; unit tests never require an API key or network
connection.

Coverage includes:

- correct base URL, endpoint path, query parameters, and Bearer header;
- absence of the API key from errors and terminal output;
- missing-key failure before transport invocation;
- response handling for `200`, `401`, `403`, `429`, other errors, and invalid
  JSON;
- exactly three total attempts for repeated `429` responses;
- no retry for non-`429` failures;
- default date calculation and explicit date validation;
- summary extraction that omits missing fields;
- deterministic JSON output naming and content;
- CLI exit statuses and user-facing messages.

After unit tests pass, a live smoke test will run the default RTY command using
the locally supplied key. Success requires HTTP `200`, a JSON object, and a
saved response file. The live response is not committed.

## Acceptance Criteria

The first version is complete when:

1. `.env` is ignored and the key is never printed.
2. `uv run pytest` passes.
3. Running the CLI without a key fails safely before network access.
4. Running the CLI with the user's local key successfully calls Edgeful or
   reports the exact authentication or plan restriction returned by Edgeful.
5. A successful live request saves the full JSON response and prints only
   headline fields present in that response.
6. The README documents setup, key placement, the default command, overrides,
   output location, and known Edgeful plan/rate-limit constraints.
