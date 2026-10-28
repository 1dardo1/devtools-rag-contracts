# Event inventory

**What this is.** A description of every event the system publishes, **as the
code writes it today**, with the source of every claim. It is the input to
Phase 3, not its output: nothing here is a schema, and nothing here has been
versioned.

**Why it exists.** The ingestion service is ahead of this repository. It already
writes `DocumentIngested` to its outbox, so most of the event's shape is fixed by
code that runs, not by a decision still to be taken. Phase 3 has to start from
what is true. Reading five files in another repository to find out is how a
contract ends up disagreeing with its producer.

**How to keep it honest.** Every claim names a file in `devtools-rag-ingestion`.
If the code there changes, this file is wrong until it is corrected, and the
pull request that changes the code is where to correct it.

Last checked against `devtools-rag-ingestion` `main` on 2026-10-28.

---

## The events

| Event | Producer | Consumer | Status |
|---|---|---|---|
| `DocumentIngested` | ingestion | retrieval | Written to the outbox; **never yet published** — the relay (ingestion 4.3) does not exist |

There are no others. Section 4 names two that may turn out to be needed.

---

## 1. `DocumentIngested`

**Meaning.** A document has been accepted, stored and committed, and is ready to
be indexed. It is published **once per accepted document**, and only for a
document that is stored — the outbox row and the document row are written in the
same transaction (ingestion ADR 0014, `TestTheDocumentAndItsOutboxRowAreAtomic`).

**Source of the shape:** `src/rag_ingestion/domain/events.py` (the event) and
`src/rag_ingestion/infrastructure/postgres/outbox_event_publisher.py`
(`_as_payload`, the JSON actually stored). The shape was agreed at ingestion
`ROADMAP.md` 1.4.

### 1.1 The payload as stored today

```json
{
  "document_id": "2f6b3c1e-6a3e-4c55-9d3f-7b6a1f0e9c42",
  "collection_id": "8d1e0a57-3b8c-4f0f-a2c4-55e1c0b7d913",
  "content_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "occurred_at": "2026-10-28T08:17:34.105557+00:00",
  "metadata": {
    "source_library": "pydantic",
    "doc_type": "how_to",
    "library_version": "2.9",
    "source_url": "https://docs.pydantic.dev/2.9/concepts/models/"
  }
}
```

The identifiers and the URL are illustrative. The keys, nesting and value formats
are exactly what `_as_payload` produces, and what
`tests/integration/test_outbox_publisher.py` asserts.

### 1.2 Field by field

| Field | Type on the wire | Rule | Source |
|---|---|---|---|
| `document_id` | string, UUID | Minted by ingestion (`uuid4`), never chosen by a client | `domain/document_id.py` |
| `collection_id` | string, UUID | The collection the document belongs to | `domain/collection_id.py` |
| `content_hash` | string, exactly 64 lowercase hex digits | SHA-256 of the **decoded** content bytes, computed by ingestion, never accepted from a caller | `domain/content_hash.py` |
| `occurred_at` | string, ISO 8601, always with an offset | The instant ingestion **accepted** the document; equal to `Document.ingested_at` | `domain/events.py`, ADR 0009 |
| `metadata.source_library` | string, required | Non-blank, surrounding whitespace stripped | `domain/metadata.py` |
| `metadata.doc_type` | string, one of 25 values | Closed set, see 1.3 | `domain/doc_type.py` |
| `metadata.library_version` | string or `null` | If present: non-blank, stripped. **Free text, not a parsed version** | `domain/metadata.py` |
| `metadata.source_url` | string or `null` | If present: stripped, scheme `http` or `https`, non-empty host | `domain/metadata.py` |

**Absent optional fields are `null`, not missing.** The key is always there
(`test_absent_optional_metadata_is_null_in_the_payload`).

### 1.3 `doc_type`'s 25 values

`tutorial`, `how_to`, `reference`, `explanation`, `api_reference`,
`cli_reference`, `configuration`, `specification`, `glossary`, `installation`,
`quickstart`, `example`, `cookbook`, `changelog`, `release_notes`,
`migration_guide`, `deprecation_notice`, `troubleshooting`, `faq`, `readme`,
`overview`, `architecture`, `contributing`, `blog_post`, `other`.

Lowercase strings, so a value is readable without a lookup table and survives a
reordering of the enum. **Adding one is a domain change in ingestion**, by design:
the set is closed so that an unrecognised kind cannot be stored.

### 1.4 What travels outside the payload

The outbox row is an **envelope** around the payload (ingestion ADR 0012):

| Column | Meaning |
|---|---|
| `outbox_id` | `bigint` identity, assigned at insert. The relay's publication order |
| `event_type` | The literal `"DocumentIngested"`, a constant, never `type(event).__name__` (ADR 0014) |
| `payload` | The JSON above, as `jsonb` |
| `occurred_at` | The same instant as the payload's, written from one value in one statement |
| `published_at` | `NULL` until the relay has sent the row |

**`event_type` is not in the payload, and there is no version anywhere.** Where
both travel on the stream is a Phase 3 question (section 3).

### 1.5 What it deliberately does not carry

- **The content.** A consumer is expected to fetch the bytes by `document_id`.
  Pushing up to 5 MiB through the broker per document would make Redis Streams a
  content store. Source: the docstring of `DocumentIngested`. **See gap 4.1:
  nothing can serve that fetch today.**
- **The size, the status, the collection's name.** None of them is needed to
  decide whether to index a document or how to file the result.
- **An event identifier.** There is one event per document, so `document_id`
  identifies the event. That stops being true the day a second event about the
  same document exists.

---

## 2. Delivery guarantees

These come from the outbox's design, not from Redis, and they hold whatever the
relay turns out to look like.

- **At-least-once.** The relay, as `ARCHITECTURE.md` §2 designs it, reads
  unpublished rows, publishes them and only then marks them sent, so a relay
  that crashes in between sends a row again. The consumer must be idempotent
  (principle 7). The relay is not written yet; this is the design it has to
  meet, not a behaviour anyone has observed.
- **No global ordering.** `outbox_id` is assigned at insert, not at commit, so
  under concurrency a lower id can commit after a higher one and be published
  later. Ingestion ADR 0012 says so and tells 4.3 not to assume an order.
- **No loss once committed.** A committed document always has its row; a
  rolled-back one never does.
- **Arbitrary delay.** The relay publishes later — a second, or twenty minutes if
  the broker was down. That is why `occurred_at` is the instant of ingestion, not
  of publication: stamping at publication would date the document to when the
  queue drained (ingestion ADR 0009).

### What a consumer can rely on to recognise a repeat

`document_id` identifies the document. **`content_hash` alone does not**:
deduplication in ingestion is scoped to a collection and excludes failed
documents (the partial unique index is `WHERE status <> 'failed'`, ingestion ADR
0012). The same content can be stored twice in two collections, and twice in one
collection if the first attempt failed. Each time with a new `document_id`.

---

## 3. Questions Phase 3 has to answer

None of these is answered anywhere yet. Each one is a decision with alternatives,
so each one needs a proposal.

1. **Versioning.** Where the schema version travels (a payload field, a stream
   entry field, the stream name), and what counts as a breaking change. In
   particular: **is adding a `doc_type` value breaking?** A consumer validating
   against a closed enum would refuse an event carrying a value it does not know.
2. **The stream entry.** A Redis Streams entry is a flat map of strings. Whether
   the payload goes in one field as JSON, or is flattened into several, decides
   what the relay does. Ingestion ADR 0014 wants it to stay a dumb pipe.
3. **The stream name**, and whether there is one stream per event type or one
   for everything.
4. **`event_type` and the version inside or outside the payload.** Today the
   payload is everything a consumer gets *except* its own type.
5. **The timestamp format.** "ISO 8601" is not one format. `datetime.isoformat()`
   writes `+00:00`, and **drops the fraction entirely when the microseconds are
   zero**. Ingestion's HTTP API, serialised by Pydantic, writes the same instant
   with `Z`. A consumer parsing with a fixed pattern would break about once in a
   million events.
6. **Field names.** They are the ingestion domain's. Ingestion ADR 0014 says Phase
   3 may rename them, and that `_as_payload` is the one function that changes.
7. **Who validates.** Whether the producer validates against the schema before
   writing to the outbox, the consumer after reading, or both.

**The window for answering them for free closes when ingestion 4.3 ships.** Rows
written before then have never been published, so nothing reads them. From the
first published event on, each answer changes something already on the wire.

---

## 4. Gaps: contracts the design implies and nobody has drawn

Found while reading ingestion for this inventory. Neither is resolved here, and
neither belongs to ingestion alone.

### 4.1 The consumer cannot fetch the content

`DocumentIngested` leaves out the bytes on the grounds that "a consumer that
needs the bytes fetches them by `document_id`". **No endpoint returns them.**
`GET /documents/{document_id}` returns `document_id`, `collection_id`, `status`
and `ingested_at` — no content (`api/schemas.py`, `IngestionStatusResponse`).
The retrieval service cannot index a document it cannot read.

Whatever fills this — a new endpoint, a shared store, the content in the event
after all — is either a second contract between the services or a change to this
one. It has to be decided before Phase 9 can consume anything.

### 4.2 Nothing reports indexing back

Ingestion's `Document` has a state machine — `pending → processing → indexed |
failed` (`domain/document.py`) — and `GET /documents/{id}` reports it. **Only
`pending` is ever reached**, because nothing tells ingestion that retrieval has
started, finished or failed. The transitions exist in the domain with no
contract to drive them.

Filling it means an event in the other direction, from retrieval to ingestion.
That would make ingestion a consumer too, which it is not today. Leaving it
unfilled means the status endpoint reports `pending` forever, and the API's
`202` promises a status that never moves.
