# devtools-rag-contracts

Versioned event schemas shared by the ingestion and retrieval services. Single
source of truth for the contract between them.

## Status

**There is no package yet.** Phase 3 of the build order, which creates it, has
not started; its first step is a toolchain scaffold. What this repository holds
today is the documentation that Phase 3 starts from.

The ingestion service is further ahead. It already writes `DocumentIngested` to a
transactional outbox, under the field names its domain uses. Its relay — the
process that would put that event on Redis Streams — waits on this repository.

## What crosses the wire

One event, so far: **`DocumentIngested`**, published by the ingestion service
when a document has been accepted. It carries the document's identity, its
collection, a SHA-256 fingerprint of its content and its metadata
(`source_library`, `doc_type`, `library_version`, `source_url`), plus the instant
it was ingested. **It does not carry the content itself.**

Delivery is at-least-once and unordered, so a consumer must be idempotent;
`document_id` plus `content_hash` is enough to recognise a repeat.

## How it will be consumed

Both services will install `rag_contracts` as a **pinned Git dependency** and
import its schemas rather than declaring their own. A schema copied into a
service is a second source of truth, and two sources of truth disagree.

## Where to read more

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the whole system and its build
  order.
- [`docs/COLLABORATION.md`](docs/COLLABORATION.md) — how changes are proposed,
  reviewed and merged.
- [`CLAUDE.md`](CLAUDE.md) — what is already fixed about the event, and why.
- [`devtools-rag-ingestion`](https://github.com/1dardo1/devtools-rag-ingestion) —
  the service that publishes the event.
