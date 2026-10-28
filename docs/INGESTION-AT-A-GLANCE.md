# Ingestion at a glance

**What this is.** A description of the producer as a whole: what the ingestion
service is, what state it is in, and every surface a contracts author or the
future retrieval service has to know about. It exists so that nobody working here
has to open the ingestion repository to find out.

**What it is not.** The event itself. The `DocumentIngested` payload, its
envelope, the delivery guarantees, the questions Phase 3 must answer and the two
gaps in the design are in [`EVENT-INVENTORY.md`](EVENT-INVENTORY.md), and are not
repeated here.

**Snapshot** of [`devtools-rag-ingestion`](https://github.com/1dardo1/devtools-rag-ingestion)
`main` at `501f557`, 2026-10-28, with section 3.2 brought up to `035ac0a`
(ingestion #47, which changed the refusals). Paths are relative to that repository's root;
ADR numbers are its own unless stated. If its code changes, this file is wrong
until corrected.

---

## 1. Where it stands

### 1.1 Phases

| Phase | Units | State | Source |
|---|---|---|---|
| 0 Environment | 0.1 scaffold, 0.2 CI | Done | `docs/ROADMAP.md`, ADR 0008 |
| 1 Domain | 1.1 to 1.5 | Done. `domain/` has zero external imports | `CLAUDE.md` |
| 2 Use cases | 2.1 `IngestDocument`, 2.2 `CreateCollection`, 2.3 `GetIngestionStatus` | Done, against in-memory fakes | `tests/unit/application/test_phase_two_together.py` |
| 3 Event schemas | n/a | **This repository. Not started** | `docs/ROADMAP.md` |
| 4 Infrastructure | 4.1 PostgreSQL adapter, 4.2 outbox, 4.4 HTTP, 4.5 composition root | Done | ADRs 0013, 0014, 0015, 0017 |
| | 4.3 relay, outbox to Redis Streams | **Blocked. Does not exist** | `docs/BUILD-PLAN.md` |
| 5 Containers | 5.1 `Dockerfile` | Done. CI builds and starts the image | ADRs 0019, 0020 |
| | 5.2 compose | Half done: `app`, `postgres`, one-shot `migrate`. No Redis, no relay | `compose.yaml`, ADR 0021 |
| 6 Quality | 6.1 integration tests | 53 integration tests on real containers, run in CI (not explicitly marked done in `ROADMAP.md`) | ADR 0011 |
| | 6.2 coverage | Done. Floor 99%, branch coverage on | ADR 0024 |
| | 6.3 secrets via environment | Done. `.env.example` plus guard tests | ADR 0022 |
| 7 Deployment | 7.2 public deployment | **In progress. This is the gate** | ADR 0025 |
| | 7.3 README, 7.4 ADRs | Done; ADRs are continuous (25 so far) | ADR 0023, `docs/adr/` |

Phase 4's criterion ("a row in Postgres and a message in Redis") is half met:
HTTP produces the `documents` row and its `outbox` row in one transaction; Redis
is 4.3 (`docs/BUILD-PLAN.md`). **Tests:** 303 collected, 250 unit and 53
integration (`pytest --collect-only` at `035ac0a`).

### 1.2 The gate

The retrieval repository may not be created until ingestion has **a public URL
and green CI** (`CLAUDE.md`). Green CI is met; the URL is not. The platform is
chosen (5.3) and its two pull requests are merged (#44 `render.yaml`, #45
`migrate.yml`). What remains is the owner's manual work: Neon project, GitHub
`production` Environment secret, one migration run, the Render Blueprint, then
the README's three requests against the public URL. A third pull request records
the URL. **Nothing in this repository moves the gate.**

### 1.3 What is blocked on this repository

**4.3, the relay.** `docs/BUILD-PLAN.md` draws `EXT3 --> U43`: Phase 3 here
must finish first, because the event's shape is this repository's.
`OPEN-DECISIONS.md` §2 and §6 add that this repository first needs a toolchain
scaffold. Until then the `outbox` fills and nothing drains it; every document
stays `pending` (`README.md`, "What is not done").

### 1.4 The other thing 4.3 waits on: the relay's silence

A separate, ingestion-local decision, also due before 4.3. A crashed relay and
an idle one both write nothing, so logs cannot tell them apart. ADR 0016 settled
only the logging **mechanism** (standard library `logging`, one JSON object per
line on stdout, `extra` under `context`) and split this out. The recorded
proposal (ADR 0016, `OPEN-DECISIONS.md` §3, `docs/BUILD-PLAN.md`): **the API
reports the age of the oldest unpublished outbox row.** A growing age means the
relay is not working, read through the database both processes already share,
with no new channel. A proposal, not a decision.

---

## 2. The domain the event is derived from

`src/rag_ingestion/domain/`, 14 modules, standard library only.

### 2.1 Value objects

| Type | Holds | Invariant | Source |
|---|---|---|---|
| `DocumentId` | `UUID` | Minted by ingestion with `uuid4()`, never accepted from a client. `parse(str)` raises `InvalidDocumentIdError` | `domain/document_id.py` |
| `CollectionId` | `UUID` | Same shape as `DocumentId`, deliberately a distinct type. `parse` raises `InvalidCollectionIdError` | `domain/collection_id.py` |
| `ContentHash` | `str` | Exactly 64 characters from `0123456789abcdef`. `ContentHash.of(bytes)` is SHA-256 hexdigest. Empty content hashes fine | `domain/content_hash.py` |
| `Metadata` | 4 fields | See below | `domain/metadata.py` |
| `DocType` | `StrEnum` | Closed set of 25 lowercase values (listed in [the inventory, 1.3](EVENT-INVENTORY.md#13-doc_types-25-values)) | `domain/doc_type.py` |
| `DocumentStatus` | `StrEnum` | `pending`, `processing`, `indexed`, `failed` | `domain/document_status.py` |
| `IngestionLimits` | 2 ints | Both must be positive, else `InvalidLimitError` | `domain/limits.py` |

`Metadata` (frozen); a blank optional field is refused, absence is `None`:

| Field | Type | Rule |
|---|---|---|
| `source_library` | `str` | Required. Stripped; blank after stripping raises `MissingMetadataFieldError` |
| `doc_type` | `DocType` | Required |
| `library_version` | `str \| None` | Optional. If present, stripped and non-blank. Free text |
| `source_url` | `str \| None` | Optional. If present, stripped, scheme `http` or `https`, non-empty host, else `InvalidSourceUrlError` |

### 2.2 Entities

**`Document`** (`domain/document.py`), equality and hash on `document_id` only.
Fields: `document_id: DocumentId`, `collection_id: CollectionId`,
`content_hash: ContentHash`, `size_in_bytes: int` (`>= 0`, else
`NegativeDocumentSizeError`), `metadata: Metadata`, `ingested_at: datetime`
(timezone required, else `NaiveTimestampError`; supplied by the `Clock` port),
`status: DocumentStatus = pending`. **It does not hold the content**: the bytes
travel beside it, as the second argument of `DocumentRepository.add`.

Status transitions (`_ALLOWED_TRANSITIONS`), through three methods only:

| From | Allowed to | Method |
|---|---|---|
| `pending` | `processing` | `start_processing()` |
| `processing` | `indexed` or `failed` | `mark_indexed()`, `mark_failed()` |
| `indexed` | nothing (terminal) | |
| `failed` | nothing (terminal) | |

Any other move raises `IllegalStatusTransitionError`. A failed document is
recovered by **submitting the content again**, which creates a new document with
a new `document_id`. It is never revived. **Nothing in the service calls any of
the three methods today**, so every stored document is `pending`. See
[inventory gap 4.2](EVENT-INVENTORY.md#42-nothing-reports-indexing-back).

**`Collection`** (`domain/collection.py`), equality and hash on `collection_id`.
Fields: `collection_id: CollectionId` (minted by `CreateCollection`, never
accepted from a client) and `name: str`. Name rules: surrounding whitespace is
stripped and nothing else is normalised; blank raises
`MissingCollectionNameError`; uniqueness is **exact and case-sensitive**
(`Docs` and `docs` are two collections); no length limit
(`application/create_collection.py`, migration). A collection does not hold its
documents and records no creation time (ADR 0012). Creating one publishes **no
event**: retrieval learns of collections only through the `collection_id` of
documents arriving in them (`application/create_collection.py`).

### 2.3 Limits

`IngestionLimits` defaults (`domain/limits.py`): `max_document_size_in_bytes =
5 * 1024 * 1024` (5 MiB of **decoded** content) and `max_documents_per_collection
= 10_000`. **These are the production values**: `main.py` builds
`IngestDocument` without a `policy`, and `Settings` exposes neither number.

### 2.4 The ingestion rules

`IngestDocument.execute` (`application/ingest_document.py`) runs these in order.
The first failure refuses the document, and nothing has been written yet:

1. The collection must exist (`CollectionRepository.get`), else
   `CollectionNotFoundError`. Then the service computes `ContentHash.of(content)`
   and `len(content)`; a caller never supplies either.
2. **Size:** `size_in_bytes > max_document_size_in_bytes` raises
   `DocumentTooLargeError`. Exactly 5 MiB is accepted.
3. **Count:** `count_in_collection >= max_documents_per_collection` raises
   `CollectionFullError`. **The count includes failed documents**
   (`infrastructure/postgres/document_repository.py`).
4. **Duplicate:** if the collection already holds this `content_hash` in any
   status other than `failed`, `DuplicateDocumentError`. Dedup is **per
   collection**, never service-wide (`domain/ingestion_policy.py`), and failed
   documents are excluded so they can be resubmitted.
5. A `Document` is built with a new `DocumentId`, status `pending`, and
   `ingested_at = clock.now()`, the clock being read **once**.
6. `documents.add(document, content)`, then
   `events.publish(DocumentIngested.about(document))`, on one connection, in one
   transaction committed by the caller (`main.py`, `transaction_per_request`).

The duplicate rule is enforced twice: by the query in step 4 (which gives a
readable domain error) and by the partial unique index in section 4 (which makes
it true under concurrency). The same holds for collection names.

### 2.5 The ports

`domain/ports.py`, all `typing.Protocol`, **all synchronous** (ADR 0007). Copied
exactly, docstrings removed:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...

class DocumentRepository(Protocol):
    def add(self, document: Document, content: bytes) -> None: ...
    def get(self, document_id: DocumentId) -> Document | None: ...
    def exists_with_content_hash(
        self, collection_id: CollectionId, content_hash: ContentHash
    ) -> bool: ...
    def count_in_collection(self, collection_id: CollectionId) -> int: ...

class CollectionRepository(Protocol):
    def add(self, collection: Collection) -> None: ...
    def get(self, collection_id: CollectionId) -> Collection | None: ...
    def exists_with_name(self, name: str) -> bool: ...

class EventPublisher(Protocol):
    def publish(self, event: DocumentIngested) -> None: ...
```

Adapters (`infrastructure/`): `PostgresDocumentRepository`,
`PostgresCollectionRepository`, `PostgresOutboxEventPublisher` (psycopg 3,
hand-written SQL, **none of them commits**, ADR 0013), and `SystemClock`, which
returns `datetime.now(UTC)`. There is no Redis publisher.

---

## 3. The HTTP API

`src/rag_ingestion/api/`. FastAPI, every endpoint declared `def`. The generated
OpenAPI is at `/openapi.json` and the interactive version at `/docs`. Every
request model sets `extra="forbid"`, so an unknown field is a `422`.

### 3.1 Endpoints

| Method and path | Request body | Success | Response body |
|---|---|---|---|
| `POST /collections` | `{"name": str}` | **`201`** | `{"collection_id": uuid}` |
| `POST /collections/{collection_id}/documents` | `{"content": base64 str, "metadata": {...}}` | **`202`** | `{"document_id": uuid}` |
| `GET /documents/{document_id}` | none | **`200`** | `{"document_id", "collection_id", "status", "ingested_at"}` |

Source: `api/routes.py`, `api/schemas.py`.

- **`content` is base64 inside JSON** (`Base64Bytes`); UTF-8 strings and
  `multipart/form-data` were rejected (ADR 0015). Over-padding is tolerated.
- **`metadata`** has the four fields of 2.1. `doc_type` is typed `DocType`, and
  path ids are typed `UUID`, so bad values are a FastAPI `422` before domain code.
- **`202`, never `201`, for a document**: recorded, not finished (ADR 0015).
- **No endpoint returns content, hash or size**
  ([inventory gap 4.1](EVENT-INVENTORY.md#41-the-consumer-cannot-fetch-the-content)).
- **`ingested_at` is written with `Z`** by Pydantic, e.g.
  `2026-09-13T08:17:34.105557Z` (`README.md`, `tests/unit/api/test_routes.py`),
  and **drops the fraction when the microseconds are zero**
  (`2026-10-28T08:00:00Z`, checked). The event's `occurred_at` uses `+00:00`.
  The value is read back from PostgreSQL, so its offset follows the session
  `TimeZone`, which no code sets; the `Z` was observed on `postgres:16` (UTC by
  default), not yet on Neon.
- Every response carries an **`X-Request-Id`** header, minted per request. An
  inbound one is ignored (`api/request_id.py`).

### 3.2 Refusals

**Every refusal answers `{"code": str, "detail": str}`** (`ErrorResponse`),
and every `4xx` in the OpenAPI document declares that shape. `code` is a literal string, never derived from a class name,
because renaming it on the wire is a breaking change (`api/error_handling.py`).

| Status | `code` | Raised by | Endpoint |
|---|---|---|---|
| `404` | `collection_not_found` | `CollectionNotFoundError` | `POST …/documents` |
| `404` | `document_not_found` | `DocumentNotFoundError` (HTTP layer; the use case returns `None`) | `GET /documents/{id}` |
| `409` | `duplicate_collection_name` | `DuplicateCollectionNameError` | `POST /collections` |
| `409` | `duplicate_document` | `DuplicateDocumentError` | `POST …/documents` |
| `409` | `collection_full` | `CollectionFullError` | `POST …/documents` |
| `413` | `document_too_large` | `DocumentTooLargeError` (domain) | `POST …/documents` |
| `413` | `request_too_large` | `BodySizeLimitMiddleware` (transport) | any |
| `422` | `missing_metadata_field` | `MissingMetadataFieldError` | `POST …/documents` |
| `422` | `invalid_source_url` | `InvalidSourceUrlError` | `POST …/documents` |
| `422` | `missing_collection_name` | `MissingCollectionNameError` | `POST /collections` |
| `422` | `invalid_request` | FastAPI's `RequestValidationError`: unknown or missing field, wrong type, unknown `doc_type`, bad base64, malformed path UUID | any |
| `500` | `internal_error` | any `DomainError` not in the table | any |

Sources: `api/error_handling.py`, `api/body_limit.py`. One handler answers
domain errors, the unknown document and validation failures. For
`invalid_request`, `detail` names each failing location and why
(`body.metadata.doc_type: Input should be …`) and **never echoes the input**,
which for a document is its content.

Until ingestion #47 (merged 2026-10-28) two refusals broke the shape: the unknown
document answered FastAPI's `{"detail": "…"}` with no `code`, and validation
failures answered `{"detail": [ … ]}`. A client written against an older
snapshot may still expect those.

### 3.3 Two size caps, not one

| Cap | Value | Measures | Layer | Refusal |
|---|---|---|---|---|
| `max_document_size_in_bytes` | 5 MiB | **Decoded** content bytes | Domain (`domain/limits.py`) | `413 document_too_large` |
| `max_body_bytes` | 7 MiB (7,340,032) | **Request body on the wire** | Transport (`config.py`, `api/body_limit.py`) | `413 request_too_large` |

The wire cap is larger because base64 expands content by a third, so a 5 MiB
document arrives as about 6.7 MiB of JSON. A body whose `Content-Length` exceeds
the cap is refused before it is read. A body without one (chunked) is counted as
it streams and cut off at the cap. The middleware is added last in `build`, so it
runs first. `test_the_body_cap_cannot_refuse_a_document_the_domain_accepts`
fails if the two numbers are ever set so that the wire cap shadows the domain
rule (ADR 0018). **Clients tell the two `413`s apart by `code` only**
(`OPEN-DECISIONS.md` §4.2).

---

## 4. The database schema

One revision, `0001`, in
`src/rag_ingestion/migrations/versions/v0001_create_the_initial_schema.py`. SQL
copied from it, comments removed. Reasons for each choice are in ADR 0012.

```sql
CREATE TABLE collections (
    collection_id uuid PRIMARY KEY,
    name          text NOT NULL,
    CONSTRAINT collections_name_is_not_blank CHECK (name <> ''),
    CONSTRAINT collections_name_is_unique UNIQUE (name)
);

CREATE TABLE documents (
    document_id     uuid        PRIMARY KEY,
    collection_id   uuid        NOT NULL REFERENCES collections (collection_id),
    content_hash    text        NOT NULL,
    content         bytea       NOT NULL,
    size_in_bytes   bigint      NOT NULL,
    status          text        NOT NULL,
    source_library  text        NOT NULL,
    doc_type        text        NOT NULL,
    library_version text,
    source_url      text,
    ingested_at     timestamptz NOT NULL,
    CONSTRAINT documents_content_hash_is_a_sha256_digest
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT documents_size_in_bytes_is_not_negative
        CHECK (size_in_bytes >= 0),
    CONSTRAINT documents_size_in_bytes_matches_content
        CHECK (size_in_bytes = octet_length(content)),
    CONSTRAINT documents_status_is_known
        CHECK (status IN ('pending', 'processing', 'indexed', 'failed')),
    CONSTRAINT documents_source_library_is_not_blank
        CHECK (source_library <> ''),
    CONSTRAINT documents_doc_type_is_not_blank
        CHECK (doc_type <> ''),
    CONSTRAINT documents_library_version_is_not_blank
        CHECK (library_version <> ''),
    CONSTRAINT documents_source_url_is_not_blank
        CHECK (source_url <> '')
);

CREATE UNIQUE INDEX documents_live_content_is_unique_per_collection
    ON documents (collection_id, content_hash)
    WHERE status <> 'failed';

CREATE INDEX documents_by_collection ON documents (collection_id);

CREATE TABLE outbox (
    outbox_id    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type   text        NOT NULL,
    payload      jsonb       NOT NULL,
    occurred_at  timestamptz NOT NULL,
    published_at timestamptz,
    CONSTRAINT outbox_event_type_is_not_blank CHECK (event_type <> '')
);

CREATE INDEX outbox_unpublished ON outbox (outbox_id) WHERE published_at IS NULL;
```

What a consumer should know about it (ADR 0012):

- **The content is `documents.content`**, `bytea`, beside the record; no
  separate table or object storage.
- **`doc_type` is not constrained** in the database; a misspelled value is
  storable and fails only when read back through `DocType`.
- **No `ON DELETE`** on the foreign key; nothing deletes collections or documents.
- **`outbox` has no foreign key to `documents`** and rows are never deleted;
  `published_at IS NULL` is the backlog, which the relay will set.
- **`outbox_id` orders by insert, not commit**: no global ordering
  ([inventory §2](EVENT-INVENTORY.md#2-delivery-guarantees)). **`jsonb`
  normalises** key order and whitespace.
- `timestamptz` everywhere. Tests and compose pin `postgres:16`. Migrations are
  hand-written and applied with `alembic upgrade head` (ADR 0010).

---

## 5. Configuration and runtime

### 5.1 Environment variables

| Variable | Read by | Required | Default | Meaning |
|---|---|---|---|---|
| `DATABASE_URL` | `Settings`, `migrations/env.py` | Yes | none | Plain libpq URL (`postgresql://…`). **Not** SQLAlchemy's `postgresql+psycopg://`, which `psycopg.connect` rejects; `env.py` adds that prefix for Alembic (ADR 0017) |
| `LOG_LEVEL` | `Settings` | No | `INFO` | Any `logging` level name |
| `MAX_BODY_BYTES` | `Settings` | No | `7340032` | The transport cap of section 3.3 |
| `PORT` | Render only | n/a | `8000` in `render.yaml` | Tells Render where the image listens. `Settings` does not read it |

Sources: `config.py`, `.env.example`, `render.yaml`. `Settings` has
`extra="forbid"`. A deployment's `DATABASE_URL` carries a password and lives only
in Render's dashboard (`sync: false`) and the GitHub `production` Environment
secret (ADRs 0022, 0025). No other credential exists.

### 5.2 Process model

- **One API process**: `uvicorn rag_ingestion.main:build --factory --host 0.0.0.0
  --port 8000`, one worker, non-root user, image `python:3.14-slim`
  (`Dockerfile`, ADR 0019).
- **One connection and one transaction per request**: `transaction_per_request`
  in `main.py` connects, commits on success, rolls back on any exception, closes.
  It is the whole transaction boundary. No pool (`OPEN-DECISIONS.md` §5.3); no
  connection until a request arrives.
- **The relay is a separate process with its own lifecycle**, sharing only the
  database (`CLAUDE.md`). **It does not exist yet**, nor any Redis client.
- **Logs**: one JSON object per line on stdout, uvicorn's included (ADR 0016).
- **No health endpoint.** Compose and Render probe `/openapi.json`, which proves
  the process, not the database (`OPEN-DECISIONS.md` §4.1).

### 5.3 Deployment (7.2, in progress)

| | Choice | Source |
|---|---|---|
| Compute | Render free web service, `runtime: docker`, the repository's `Dockerfile` | `render.yaml` |
| Database | Neon free PostgreSQL, **direct** URL (not the pooled PgBouncer one) | ADR 0025 |
| Region | Frankfurt for both (Render `frankfurt`, Neon AWS `eu-central-1`) | ADR 0025 |
| Deploy trigger | A commit on `main`, after its CI checks pass (`autoDeployTrigger: checksPass`) | `render.yaml` |
| Migrations | `.github/workflows/migrate.yml`: `workflow_dispatch` only, `main` only, one at a time, upgrade only. **Never at container start** (ADR 0019) | ADR 0025 |
| Local stack | `compose.yaml`: `postgres:16` with trust auth on `127.0.0.1`, a one-shot `migrate`, `app` | ADR 0021 |

Known costs from ADR 0025 that reach a consumer:

- **Two cold starts in a row.** Render sleeps the API after 15 idle minutes (up
  to about a minute to wake); Neon suspends after 5. A first request after a
  quiet spell can take close to a minute.
- **The relay will not fit.** Render's free plan has no background workers; the
  platform question reopens at 4.3, and Fly.io may win it then.
- **Writes are unauthenticated** until Phase 13, bounded by Neon's 0.5 GB.
- **The health check cannot see a wrong `DATABASE_URL`**: it deploys green and
  fails on the first real request.

---

## 6. Open decisions that touch contracts

From `OPEN-DECISIONS.md` unless noted.

| Item | What is open | Why it matters here |
|---|---|---|
| §2, §6 The relay (4.3) | Blocked on Phase 3 here and on this repository's toolchain scaffold | Phase 3 is the unblocker. The window to change the event for free closes when the relay ships |
| §3 The relay's silence | Proposal: the API reports the age of the oldest unpublished outbox row | Ingestion-only; changes its HTTP API, not the event |
| §4.1 Health endpoint | Not added; adding one is an API change | Consumers and probes depend on `/openapi.json` meanwhile |
| §4.2 Two `413`s | Whether they should share a status; told apart by `code` | Any client of the HTTP API |
| §6 Corpus collection | Nobody has scheduled gathering the documents | Retrieval's evaluation phase cannot run without them |
| ADR 0025 The relay's platform | Render free cannot run a worker | Decided again at 4.3 |
| [Inventory §3, §4](EVENT-INVENTORY.md#3-questions-phase-3-has-to-answer) | Versioning, stream shape, content fetch, status feedback | Owned here |

---

## 7. Discrepancies between ingestion's documents and its code

Found while writing this file, against commit `501f557`. None is fixed here.
Item 1 is fixed in ingestion; ingestion #48 corrects items 2, 3 and 4.

1. ~~**`README.md` says "every refusal answers with the same shape".**~~ Two did
   not; **fixed by ingestion #47**, merged (section 3.2).
2. **`IngestDocument.execute`'s docstring says a too-large submission "is refused
   without touching the database at all".** The collection lookup runs first, so
   one query is made before the size check (`application/ingest_document.py`).
3. **`OPEN-DECISIONS.md`'s glossary says there are twenty-four ADRs**; there are
   25. **`docs/BUILD-PLAN.md` says "eight ADRs are written"** in two places.
4. **ADR 0012 says `doc_type` has twenty-six members**; the enum has 25. Already
   recorded in the inventory.
