# Ingestion decisions

**What this is.** A digest of all 25 architecture decision records in
`devtools-rag-ingestion`, one section each, in order, so that nobody working here
has to go and read them there. **As of** ingestion `main` on 2026-10-28. Where a
record states a fact that matters to the contract, the code under
`src/rag_ingestion/` was checked the same day; disagreements are marked
**Discrepancy** and collected at the end.

**Every ADR number here is ingestion's.** This repository's `docs/adr/` is
numbered separately, so "0003" names a different decision in each. Full records:
<https://github.com/1dardo1/devtools-rag-ingestion/tree/main/docs/adr>.

**Not repeated here:** the event's fields, the envelope's columns, the delivery
guarantees and Phase 3's seven questions, all in
[`EVENT-INVENTORY.md`](EVENT-INVENTORY.md).

**Verdicts.** *directly*: fixes something about the event, its timestamps,
identity, delivery, the outbox envelope, package naming, or the relay.
*toolchain*: a choice the contracts scaffold will likely mirror or consciously
reject — a starting point, not a decision made here (`CLAUDE.md`). *no*:
ingestion-only, summarised so a reader knows it exists.

---

## The 25 records

| ADR | Title | Binds contracts |
|---|---|---|
| 0001 | Record architecture decisions | toolchain |
| 0002 | Target Python 3.14 | toolchain |
| 0003 | Use a src layout with `rag_ingestion` as the import root | **directly** |
| 0004 | Use hatchling as the build backend | toolchain |
| 0005 | Close the three gaps that `mypy --strict` leaves open | toolchain |
| 0006 | Select `ruff` rules deliberately rather than by default or in bulk | toolchain |
| 0007 | Keep this service's ports synchronous | no |
| 0008 | Run every local check again on a clean machine, on every proposed change | toolchain |
| 0009 | Read the clock once, through a port, and let the instant travel | **directly** |
| 0010 | Reach PostgreSQL with psycopg 3 and hand-written SQL, migrate with Alembic | no |
| 0011 | Let integration tests start their own containers | toolchain |
| 0012 | The initial database schema | **directly** |
| 0013 | The PostgreSQL repositories take a connection and never commit | **directly** |
| 0014 | The outbox row, its payload, and who owns the contract | **directly** |
| 0015 | The HTTP layer: FastAPI, base64 content, and per-request use cases | no |
| 0016 | Structured logging on the standard library | **directly** |
| 0017 | The composition root | **directly** |
| 0018 | The body-size cap | no |
| 0019 | The container image | no |
| 0020 | The image is built and started in CI | no |
| 0021 | The compose stack | no |
| 0022 | Secrets live in the environment, and a guard says so | toolchain |
| 0023 | The README shows the API, and a guard holds it | no |
| 0024 | Coverage is measured in CI, and it has a floor | toolchain |
| 0025 | The public deployment: Render for compute, Neon for PostgreSQL | **directly** |

---

## 0001. Record architecture decisions

**Binds contracts:** toolchain — a process convention `COLLABORATION.md` already
applies here.

Nygard-format ADRs for any decision expensive to reverse — a technology, a
service boundary, **a contract**. Each names at least one rejected alternative
and one negative. **Records are edited in place, not superseded**, so `docs/adr/`
holds only decisions in force; each carries **`Last revised`** (when last known
true), not a creation date. Rejected: no record; one design document; immutable
records with "superseded" chains. Negatives: cost at peak momentum, retroactive
justification, silent staleness, history pushed into `git log`.

## 0002. Target Python 3.14

**Binds contracts:** toolchain.

`requires-python = ">=3.14"` — a floor, not a pin; ruff `target-version =
"py314"`, mypy `python_version = "3.14"`, `.python-version` `3.14`. Rejected:
3.12 (security-only since April 2025) and 3.13 (bugfix window closes around
October 2026); 3.14 runs to about October 2027 and has PEP 649/749 deferred
annotations. Negatives: PEP 649 changes when annotations are evaluated, and
Pydantic introspects them heavily with less mileage on 3.14; some sandboxes offer
only `3.14.0rc2`, on which Pydantic cannot import (`_eval_type() got an
unexpected keyword argument 'prefer_fwd_module'`, per ingestion's `CLAUDE.md`).
**For contracts:** a library *is* installed into other environments, so a floor
rather than a pin matters more here than in a service.

## 0003. Use a src layout with `rag_ingestion` as the import root

**Binds contracts:** directly — it names this repository's import root.

**Decided.** One package, `src/rag_ingestion/{domain,application,infrastructure,api}/`.
Distribution `devtools-rag-ingestion`, import root `rag_ingestion`. The short root
"establishes a prefix shared by the sibling repositories — `rag_ingestion`,
`rag_contracts`, `rag_retrieval` — which makes the origin of any import obvious
at a glance once Phase 3 introduces the contracts package as a dependency".
PyPI was checked on 2026-08-28 for ingestion's names only; **`rag-contracts` and
`devtools-rag-contracts` were not checked**. **Rejected.** Four top-level
packages (`domain`, … are published names, open to shadowing); a flat layout
(tests import the tree, not the wheel); `src/devtools_rag_ingestion/` (an
uninformative prefix). **Negatives.** The two names differ, which **defeats the
build backend's package detection** (0004); the package must be installed before
tests run.

**For contracts.** The analogue is distribution `devtools-rag-contracts`, import
root `rag_contracts`, under `src/`. Consumers install it from Git, so testing the
installed artifact rather than the tree matters more here.

## 0004. Use hatchling as the build backend

**Binds contracts:** toolchain.

`build-backend = "hatchling.build"` plus exactly one setting,
`[tool.hatch.build.targets.wheel] packages = ["src/rag_ingestion"]`, which is
required because the names differ (0003) — without it, `Call to
hatchling.build.build_editable failed`. A third hatch line "should be treated as
a decision, not a detail". Rejected: setuptools (three configuration eras);
`uv_build` (youngest, minimal, tied to one frontend — hatchling keeps `pip
install .` working). **For contracts:** consumers build from a Git URL with their
own frontend, so that independence is a real requirement; and hatchling
**validates that every file `pyproject.toml` names exists** (0019).

## 0005. Close the three gaps that `mypy --strict` leaves open

**Binds contracts:** toolchain.

`strict = true`, `files = ["src", "tests"]`, `warn_unreachable = true`,
`enable_error_code = ["ignore-without-code", "redundant-expr",
"possibly-undefined", "truthy-bool"]`. Untyped libraries fail
(`ignore_missing_imports` stays `false`; exceptions are per-module overrides);
`tests/` is checked because ports are structural `Protocol`s and only that proves
the fakes match; a bare `# type: ignore` is an error. Rejected: `--strict` alone
with `ignore_missing_imports = true`; leaving `tests/` unchecked. Negatives:
slower test writing; noisy error codes; overrides route around it unseen.
**Discrepancy (minor):** `pyproject.toml` also sets `mypy_path = "src"`, absent
from the ADR. **For contracts:** 0017 rejected **`plugins = ["pydantic.mypy"]`
on evidence** — with it, mypy stopped reporting a wrong argument type to a model
constructor (`CreateCollectionRequest(name=123)`).

## 0006. Select `ruff` rules deliberately rather than by default or in bulk

**Binds contracts:** toolchain.

Default formatter; twenty-three families: `E W F I N UP B S A C4 D DTZ T20 SIM
RUF PT TID PTH TRY LOG G ARG EM`; `ignore = ["D105", "D107"]`; pydocstyle
`convention = "pep257"` (required, or D203/D211 and D212/D213 conflict);
`"tests/**" = ["S101", "ARG001", "ARG002", "D"]`. `DTZ` because outbox
timestamps reach PostgreSQL, `S` so Phase 13 is not a retrofit, `TID` to ban
relative imports, `T20` because a `print` is a data escape. Renaming an unused
port parameter to `_x` in a fake type-checks but fails under keyword calls, hence
the `ARG` exemption in tests.

**Excluded:** `ANN` (mypy covers it); **`TC`, which "can break the runtime
annotation introspection Pydantic depends on"**; `COM`, `ISC`, `RET`, `FBT`,
`ERA`, `PL`. Rejected: ruff's defaults (four families); `select = ["ALL"]`.
Negatives: maintenance; broad exemptions; a snapshot of ruff 0.16.5. **For
contracts:** the `TC` exclusion is the one that matters for a package of Pydantic
models; `G` and `LOG` lint only `logging` and would sit idle here.

## 0007. Keep this service's ports synchronous

**Binds contracts:** no.

Ingestion's ports, use cases, adapters and endpoints are synchronous. One line
reaches beyond it: **"The retrieval service should be asynchronous"**, since it
waits on a language model. A schema package should force neither style.

## 0008. Run every local check again on a clean machine, on every proposed change

**Binds contracts:** toolchain.

`.github/workflows/ci.yml` on every pull request and push to `main`: `uv sync
--locked --all-groups` (itself a check of lockfile drift), then `ruff check`,
`ruff format --check`, `mypy`, tests — named steps in **one job**, each after the
first under `if: ${{ !cancelled() }}`. Actions **pinned by commit SHA** with the
version in a comment (`astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d
# v10.0.1`; there is no floating `@v10` tag); `uv` pinned to `0.12.10`;
`permissions: contents: read`; superseded pull-request runs cancelled, `main`
never. Rejected: the checklist alone; `pre-commit` as primary (`--no-verify`);
four jobs (repeated setup); one script (first failure hides the rest). Later
rules: a new job only if it would not repeat the `uv` setup (0020, 0021);
`!cancelled()` for independent checks, not sequences (0020); tests now run under
`coverage` (0024). Negatives: pinned SHAs rot; nothing checks `ci.yml` itself.

## 0009. Read the clock once, through a port, and let the instant travel

**Binds contracts:** directly — it defines what `occurred_at` means.

**Decided.**

- **`Clock` is a port** in `rag_ingestion.domain.ports`: one `now()` returning a
  timezone-aware `datetime`.
- **It is read exactly once per ingestion**, in `IngestDocument.execute`, and a
  test asserts the count. Verified: `self.clock.now()` in
  `application/ingest_document.py` is the only call in `src/`.
- **The instant becomes `Document.ingested_at`**, and
  **`DocumentIngested.about(document)` derives `occurred_at` from it**, taking no
  instant of its own, so the record and the announcement cannot disagree.
- **Naive timestamps are refused** by `Document` and by `DocumentIngested`
  (`NaiveTimestampError`), the runtime half of ruff's `DTZ`.

**On the wire.** The relay publishes later — "a second later, or twenty minutes
later if the broker was down". `occurred_at` is **the instant of ingestion, never
of publication**; stamping at publication "would make the event say the document
arrived when the queue drained".

**Rejected.** An ambient `datetime.now(UTC)`; `freezegun`/`monkeypatch`; the
HTTP layer supplying the instant; two reads for entity and event (can differ
under load); **the event or the publisher stamping itself** — a second clock,
moving "what is announced" into infrastructure "when Phase 3 puts the schema in
the contracts repository". **Negatives.** A clock injected into every
time-recording use case; the timezone check duplicated. **Status transitions
carry no time**: `start_processing`, `mark_indexed` and `mark_failed` record
that a document moved, not when — "the first thing to revisit when 4.3 exists",
and relevant if an indexing-result event is designed (inventory gap 4.2). The
serialised format is settled by 0014 and 0017; see inventory question 5.

## 0010. Reach PostgreSQL with psycopg 3 and hand-written SQL, migrate with Alembic

**Binds contracts:** no.

psycopg 3 with hand-written SQL; rows are rebuilt through the domain's own
constructors. Alembic runs `op.execute(...)` migrations with no declared models,
so no `autogenerate`. The SQLAlchemy ORM was rejected on evidence (`slots=True`
entities fail with `cannot create weak reference`); SQLAlchemy still arrives
transitively through Alembic.

## 0011. Let integration tests start their own containers

**Binds contracts:** toolchain — most likely rejected; nothing here needs one.

`testcontainers[postgres]` in the `dev` group, a container per test on a random
port; **the `redis` extra belongs with 4.3**. Container tests are marked, with
`addopts = "--strict-markers"` and `markers = ["integration: starts a real
container; needs a Docker daemon"]`, so a mistyped marker fails collection.
Rejected: a CI service container plus compose (two definitions); a
`compose.test.yaml`; `pytest-postgresql` (a local process, not a container);
`pytest-docker` (no 3.14). Negative: no Docker, no integration run.

## 0012. The initial database schema

**Binds contracts:** directly — the outbox envelope, publication order and the
deduplication rule.

The schema's job is "to restate the rules the domain already has, in the one
place the domain cannot reach". Revision `0001` creates `collections`,
`documents` and `outbox`. The outbox as created in code (column meanings in
[`EVENT-INVENTORY.md`](EVENT-INVENTORY.md) §1.4):

```sql
outbox_id    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
event_type   text        NOT NULL,  -- CHECK (event_type <> '')
payload      jsonb       NOT NULL,
occurred_at  timestamptz NOT NULL,
published_at timestamptz,
-- CREATE INDEX outbox_unpublished ON outbox (outbox_id) WHERE published_at IS NULL
```

**Envelope, not payload.** The schema commits to the envelope and leaves the
payload opaque, because "Phase 3 fixes the published payload in
`devtools-rag-contracts`". The partial index holds only the backlog. Rejected:
deleting a row once published (loses the audit trail); a UUID key (no order, and
the relay publishes oldest-first); `json` or `text` (`jsonb` guarantees valid
JSON); **a foreign key to `documents`** — the outbox is event-type-agnostic and
must not be tied to the lifetime of what it records. (The non-blank `event_type`
check is in the code, not in the ADR.)

**Deduplication** is a partial unique index,
`documents_live_content_is_unique_per_collection ON documents (collection_id,
content_hash) WHERE status <> 'failed'`. A total index was rejected because a
failed document must be resubmittable. So a `content_hash` is unique only among
*live* documents in *one* collection (consumer consequence: inventory §2).
Status is `text` with `CHECK (status IN ('pending', 'processing', 'indexed',
'failed'))`: an `ENUM` is hard to undo, and free text would let a misspelled
`'failed'` silently break deduplication.

**`doc_type` is deliberately not constrained** — each addition would be a
migration and nothing branches on it, so an unknown value fails on read through
`DocType`. **Discrepancy:** the ADR says it "has twenty-six members";
`domain/doc_type.py` has **25** (inventory §1.3).

Also: content as `bytea`; no `DEFAULT now()` anywhere (it would read a clock
behind the domain's back, against 0009); **`timestamptz`, never `timestamp`**.

**Negatives that bind Phase 3.** **"The outbox orders by assignment, not by
commit"**, so "strict global ordering is not a guarantee this schema makes, and
4.3 should not assume one". And **"the payload column exists before its contents
are agreed"**: nothing in ingestion can validate the `jsonb`.

## 0013. The PostgreSQL repositories take a connection and never commit

**Binds contracts:** directly — it is what makes "an event exists if and only if
its document was stored" achievable.

**Decided.** `PostgresDocumentRepository` and `PostgresCollectionRepository` take
a `psycopg.Connection`; **neither commits nor rolls back**. The boundary belongs
to the connection's owner (since 0017, the composition root). `get` does not
select `content`. Verified: nothing under `infrastructure/` calls `commit()` or
`rollback()`.

**Rejected.** A pool or URL per repository (each call its own transaction, so
never atomic); a unit of work (premature); committing after each write; a
repository-level `commit()`. **Proof:** `TestTheTransactionBelongsToTheCaller`
writes through two repositories on one connection, rolls back, and checks from a
second connection that nothing survived; one added `commit()` fails it.

**Negatives.**

- **An autocommit connection silently breaks the invariant**; no signature can
  exclude it, and ingestion's own fixture uses `autocommit=True`. No runtime
  guard exists in `src/`.
- Pooling is nobody's job; mypy cannot see the row-to-entity mapping.
- **A lost race is a driver error.** Two concurrent submissions of one content
  can both pass the existence check; the partial index then raises
  `UniqueViolation`. Translating it was left for later; on 2026-10-28 nothing in
  `src/` does, so from the code the caller appears to get a `500`. Either way
  **the losing transaction rolls back and writes no event**.

## 0014. The outbox row, its payload, and who owns the contract

**Binds contracts:** directly — the most important record for Phase 3.

The build plan reads `U41 --> U42 --> U43` and `EXT3 --> U43`: **only the relay
waits on Phase 3**, because only the relay puts a message on the wire.

- `PostgresOutboxEventPublisher` takes a connection, never commits, and runs
  `INSERT INTO outbox (event_type, payload, occurred_at) VALUES (%s, %s, %s)`;
  `published_at` is left out, not set to `NULL`.
- **`publish` must never contact a broker**, "because a socket cannot be rolled
  back".
- **`_EVENT_TYPE = "DocumentIngested"`**, never `type(event).__name__`: a class
  rename is a refactor, a rename on the wire is a breaking change.
- **The payload is the event's five fields under the domain's names**, UUIDs as
  strings, `occurred_at` via `.isoformat()` (inventory §1.1); explicit because
  psycopg's `Jsonb` refuses a raw `UUID` or `datetime`.
- **`occurred_at` is stored twice**, column and payload, from one value in one
  `INSERT`.
- **"Phase 3 owns the contract — versioning, a formal schema, any renaming — and
  `_as_payload` is the single function it changes."**

**Rejected.** Inventing a wire format now (version envelope, `type`/`data`
split, renamed keys): a second shape, guessed in the repository that does not
own it. Waiting for Phase 3: contradicts the build plan. **`occurred_at` as a
column only, merged in by the relay: it would make the relay decide the
message's shape** — "The relay should be a dumb pipe — read a row, send its
payload, mark it sent — because a pipe that assembles messages is a second place
the contract lives." Payload only: the envelope loses a typed `timestamptz`. A
unit of work: connection injection already gives one transaction.

**Proof.** `TestTheDocumentAndItsOutboxRowAreAtomic` runs the real
`IngestDocument` on three adapters sharing one connection: one commit makes both
rows durable; a rollback or a real `UniqueViolation` loses both.

**Negatives.**

- The invariant is only as strong as 0017's wiring; no type protects it.
- **"The window closes when 4.3 ships."** "If Phase 3 is still outstanding when
  4.3 is built, that ordering is the thing to revisit, not this shape."
- **"Was this document announced?" is not cheap**: no `document_id` column, so it
  takes `payload->>'document_id'` unindexed; such a column is "the obvious thing
  to add if operational reality disagrees".
- **`jsonb` normalises key order**; it matters only if a payload is ever signed.

**For Phase 3.** Since the relay should publish the stored payload unreshaped,
`event_type` and any version must either enter the payload via `_as_payload` or
travel from envelope columns — inventory question 4.

## 0015. The HTTP layer: FastAPI, base64 content, and per-request use cases

**Binds contracts:** no — the HTTP API is ingestion's own (`CLAUDE.md`).

`POST /collections` → `201`; `POST /collections/{collection_id}/documents` →
`202`, never `201`; `GET /documents/{document_id}` → `200`/`404`; content base64
in JSON; refusals `{"code", "detail"}`. Two points touch this repository: the
status response carries no content, so **nothing serves the
fetch-by-`document_id` the event relies on** (inventory gap 4.1); and Pydantic
writes `ingested_at` with `Z` where the outbox writes `+00:00` (question 5).

## 0016. Structured logging on the standard library

**Binds contracts:** directly — it holds the relay-silence decision due before
4.3, the moment the contract goes live.

**Decided: the mechanism only.** Standard-library `logging` with a JSON formatter
in `rag_ingestion/observability.py`; one object per line on stdout; caller
`extra` nested under **`context`** so it cannot overwrite envelope keys ("the
same envelope-and-payload split the outbox uses"). Envelope keys in code:
`timestamp`, `level`, `logger`, `message`, and `exception`, `stack`,
`request_id` when present. `configure` uses `force=True` and
`json.dumps(default=repr)`. Rejected: `structlog`; `loguru`; OpenTelemetry
(revisit at Phase 9, "once there are two services talking to each other").

**The open half.** "A relay that has crashed writes nothing. A relay with an
empty outbox also writes nothing." Something must speak when there is nothing to
say. **"Due before 4.3."** One option is recorded as a proposal, not a decision:
the API reports **the age of the oldest unpublished outbox row** — the relay's
liveness measured through the database both processes share. Still open on
2026-10-28, so 4.3 is blocked twice: on Phase 3 here, and on this. Other
negatives: nothing redacts secrets; `default=repr` is lossy.

**Discrepancy.** The ADR says "there is no request or correlation identifier".
0017 added one — `api/request_id.py` mints a `uuid4`, returns it as
`X-Request-Id`, and the formatter puts `request_id` in the envelope — but 0016
was not corrected in place.

## 0017. The composition root

**Binds contracts:** directly — it wires the atomicity of document and event, and
chooses the clock behind `occurred_at`.

**Decided.**

- `Settings` (`pydantic-settings`, `extra="forbid"`): `database_url`,
  `log_level`, `max_body_bytes`.
- `transaction_per_request(database_url)` is the **entire** transaction boundary:
  `psycopg.connect`, `yield`, `commit()`; `rollback()` on an exception; `close()`
  in `finally`. Typed `Generator`, since FastAPI throws into a `yield` dependency.
- `build(settings=None)` configures logging, adds the request-id middleware and
  overrides the providers. **All three adapters share one per-request
  connection**, because FastAPI caches `unit_of_work` per request.
- **`SystemClock` returns `datetime.now(UTC)`**, so every `occurred_at` is UTC
  and serialises with `+00:00`.
- **`DATABASE_URL` is a plain libpq URL**; `env.py` adds the
  `postgresql+psycopg://` prefix, which `psycopg.connect` rejects.

**Rejected.** Two database variables; a SQLAlchemy-form URL; the boundary as a
closure in `build` (tests cannot reach it); honouring an inbound `X-Request-Id`
(attacker-chosen text in every log line); `plugins = ["pydantic.mypy"]`.
**Proof and negatives.** An HTTP post produces the document and its outbox row,
`published_at` null (the Redis half is 4.3).
**Every domain refusal is raised before the first write**, so refusal tests do
not exercise the rollback; `TestTheTransactionBoundaryItself` drives the
generator directly. No connection pool; a forgotten override is a runtime `500`.

## 0018. The body-size cap

**Binds contracts:** no.

An outermost pure-ASGI middleware refuses requests over `max_body_bytes` (7 MiB
on the wire) before reading them: `413`, `request_too_large`. Distinct from the
domain's 5 MiB limit on decoded content (`document_too_large`) — the figure behind
the event not carrying content.

## 0019. The container image

**Binds contracts:** no.

Two stages on `python:3.14-slim`, `uv` (CI's pin) only in the build stage, `uv
sync --locked --no-dev`, non-root, one uvicorn worker, **no migrations at
start**; uvicorn's loggers are reclaimed so all output is JSON on stdout. Its
`LICENSE` lesson — "every path `pyproject.toml` points at has to be in the
image" — applies to any hatchling build. **Discrepancy (minor):**
`uvicorn[standard]` was rejected partly to keep `python-dotenv` out as "a second
configuration mechanism", but `pydantic-settings` 2.15.0 depends on it
(`uv.lock`) and `Settings` sets `env_file=".env"`, so it is installed anyway.

## 0020. The image is built and started in CI

**Binds contracts:** no.

A second CI job, `image`: `docker build`, `docker run` with `DATABASE_URL`
pointing at nothing, poll `/openapi.json`. Allowed under 0008's rule (no shared
`uv` setup); sequential steps, so no `!cancelled()`. Not a required check.

## 0021. The compose stack

**Binds contracts:** no.

`compose.yaml`: `postgres:16`, a one-shot `migrate`, `app`; trust authentication
on `127.0.0.1`; a CI job posts a document through it. **No Redis and no relay** —
"a Redis nothing reads from passes its health check while making the outbox look
drained". Both come with 4.3.

## 0022. Secrets live in the environment, and a guard says so

**Binds contracts:** toolchain — only if this repository ever holds a value worth
guarding.

`.env.example` lists exactly `Settings`' fields. Three tests in
`tests/unit/test_no_secret_is_committed.py`: a scan of `git ls-files --cached
--others --exclude-standard` (tracked-only gave a false pass) for six shapes (a
password URL, a private key, AWS and GitHub tokens, an OpenAI-style key, a
secret-named assignment); a test that each pattern matches a sample; a test that
the example names every setting. **No placeholder allowance**; the guard's file
and `uv.lock` are excluded. Rejected: gitleaks in CI. Finding: `\b` does not
match inside `POSTGRES_PASSWORD`, since `_` is a word character.

## 0023. The README shows the API, and a guard holds it

**Binds contracts:** no.

Three `curl` commands run against a real server, and a test holding routes,
fields and refusal codes in both directions. Running them found `ingested_at` is
`…T08:17:34.105557Z`, not `+00:00` — invisible to a name guard. The two-way guard
is a pattern this repository's docs could mirror.

## 0024. Coverage is measured in CI, and it has a floor

**Binds contracts:** toolchain.

`coverage.py` directly (`coverage run -m pytest`), `source = ["rag_ingestion"]`,
`branch = true`, `fail_under = 99`; the report is written to
`$GITHUB_STEP_SUMMARY` unenforced, then enforced. The floor is the whole suite's
measured 99.86% **rounded down**, since `fail_under` compares the unrounded
value; one unreachable branch stays visibly uncovered rather than pragma'd.
Rejected: `pytest-cov` (a wrapper); Codecov/Coveralls (the first secret);
report-only; 100%, 80%, 98, 93. Negatives: locally the floor needs Docker;
raising it is manual. **For contracts:** with no Docker split, one floor holds
everywhere.

## 0025. The public deployment: Render for compute, Neon for PostgreSQL

**Binds contracts:** directly — on the relay's platform, which decides where and
when the contract first goes live.

**Decided.** Render's free web service runs the image from `render.yaml`
(`PORT=8000`, `autoDeployTrigger: checksPass`, health check `/openapi.json`);
Neon's free PostgreSQL (0.5 GB) via its **direct** URL, not PgBouncer; both in
Frankfurt; `DATABASE_URL` set in Render's dashboard (`sync: false`). Migrations
run from `.github/workflows/migrate.yml` (`workflow_dispatch`, `main` only,
`production` Environment, never concurrent, no downgrade). **7.2 is not done**
until the README's three requests succeed against the public URL. Rejected:
Fly.io (no free allowance, though it "fits this architecture better"); Cloudflare
(cannot run synchronous psycopg); Render's PostgreSQL (deleted after 30 days);
dashboard-only configuration; migrating on merge or via `preDeployCommand`.

**Negatives that reach this repository.**

- **"The relay will not fit."** Render's free plan covers web services only.
  **"So 4.3 reopens the platform question, and Fly.io may win it then."** The
  first publication of `DocumentIngested` waits on a platform decision.
- An unauthenticated public write endpoint until Phase 13, bounded by Neon's
  0.5 GB; events from anonymous callers look like any others.
- **The secret scanner is deferred again** until "the first credential of a
  shape the guard does not know, an LLM API key in the retrieval service being
  the likeliest". Also: two cold starts in a row; a health check blind to a
  wrong `DATABASE_URL`.

---

## Discrepancies found

| ADR | Claim | Code on 2026-10-28 |
|---|---|---|
| 0012 | `doc_type` "has twenty-six members" | `domain/doc_type.py` has 25 |
| 0016 | "there is no request or correlation identifier" | Added by 0017 (`request_id` in the log envelope, `X-Request-Id`); 0016 not corrected |
| 0005 | The configuration block shown | `pyproject.toml` also sets `mypy_path = "src"` |
| 0019 | Rejecting `uvicorn[standard]` keeps `python-dotenv` out | `pydantic-settings` depends on it; `Settings` reads `env_file=".env"` |
| 0012 | The outbox's constraints | Code also has `CHECK (event_type <> '')` — an omission, not a contradiction |

Not a discrepancy, but open: 0013 left the translation of a lost-race
`UniqueViolation` for later, and on 2026-10-28 nothing in `src/` translates it.
