# CLAUDE.md — devtools-rag-contracts

You are working on the **contracts package** of the Devtools RAG system.

## Read first

1. `docs/COLLABORATION.md` — the working agreement. It overrides your defaults.
   Propose before implementing. Never commit to `main`. Every change goes through
   a pull request. Every proposal names a rejected alternative.
2. `docs/ARCHITECTURE.md` — the full system: three repositories, why they are
   split, and the build order. Phase 3 is this repository's.

Both are copies of the files in `devtools-rag-ingestion/docs/` and are kept
identical to them; each carries a header saying how to check. ADR numbers inside
them that name no repository are the ingestion service's.

3. `docs/adr/` — this repository's ADRs: 0001 how records are kept across
   repositories, 0002 two services and a contracts package, 0003 events through
   a transactional outbox, 0004 Redis Streams, 0005 the corpus, 0006 this
   repository's toolchain and where it differs from ingestion's.
4. `docs/EVENT-INVENTORY.md` — `DocumentIngested` as ingestion writes it today,
   field by field. **Where Phase 3 starts.**

**Everything relevant from the ingestion repository is here, so it should not
need opening.** Reach for these when the question is about the producer:

| File | Answers |
|---|---|
| `docs/INGESTION-AT-A-GLANCE.md` | What ingestion is now: phases, domain, ports, HTTP API and refusal codes, schema, configuration, deployment |
| `docs/INGESTION-DECISIONS.md` | All 25 ingestion ADRs, each marked as binding the contract directly, a toolchain choice, or ingestion-only |
| `docs/TOOLCHAIN-REFERENCE.md` | Ingestion's exact tool configuration and CI, and its known traps — the input to this repository's scaffold |

All three are snapshots of ingestion `main` on 2026-10-28. When ingestion
changes something they describe, the pull request that changes it is where to
correct them.

## What this repository is

The **single source of truth for what crosses the wire** between the ingestion
service and the retrieval service. Once Phase 3 is built, that means:

- Pydantic v2 schemas for every published event.
- Semantic versioning, with a written backward-compatibility policy.
- An installable package, `rag_contracts` (ingestion ADR 0003 set that prefix
  for all three import roots: `rag_ingestion`, `rag_contracts`, `rag_retrieval`), consumed by both services as a
  **pinned Git dependency**.
- The **system-wide ADRs**, in `docs/adr/`. Ingestion's `CLAUDE.md` says so, and
  its README already links here for the corpus decision.

Principle 6 of `ARCHITECTURE.md` is the reason the repository exists: event
schemas live **only** here. Copying a schema into a service defeats the split.

## What this repository is NOT

- **It is not a service.** No process, no endpoint, no Dockerfile, no database.
- **It has no infrastructure clients.** No Redis client, no psycopg, no Qdrant
  client, no FastAPI. A schema describes a message; sending it is a service's job.
- **It does not hold the ingestion service's public HTTP API.** Requests and
  responses of `POST /collections`, `POST /collections/{id}/documents` and
  `GET /documents/{id}` belong to that service (its ADR 0015). Only what one
  service publishes for the other to consume lives here.
- **It does not invent shapes ahead of the domains that produce them.** Phase 3
  comes after Phase 1 because the event is *derived* from the ingestion domain.
  A field that no domain needs is a guess, and a guess on the wire is permanent.

## What is already fixed, and where

The ingestion service is ahead of this repository. It already writes the event to
its outbox, so these points are **constraints Phase 3 inherits, not choices it
gets to make**. Each one has a source; read it before arguing with it.

- **One event exists: `DocumentIngested`**, with five fields — `document_id`,
  `collection_id`, `content_hash`, `metadata`, `occurred_at`. Its shape was
  agreed at ingestion `ROADMAP.md` 1.4. Source: `domain/events.py` there.
- **It does not carry the content.** A consumer fetches the bytes by
  `document_id`. Redis Streams is not a content store.
- **Delivery is at-least-once**, through a transactional outbox and a relay.
  The consumer must be idempotent (principle 7). `document_id` identifies a
  repeat; **`content_hash` alone does not**, because the same content can be
  stored again under a new `document_id` — in another collection, or after a
  failed attempt (inventory §2).
- **There is no global ordering guarantee.** Outbox identity values are
  assigned at insert, not at commit, so two events can be published out of
  order. Ingestion ADR 0012.
- **`occurred_at` is the instant of ingestion, never of publication**, and is
  always timezone-aware. Ingestion ADR 0009.
- **`event_type` is a literal string, `"DocumentIngested"`**, not derived from a
  class name, because a rename on the wire is a breaking change. Ingestion
  ADR 0014.
- **The payload today uses the domain's own field names**, with UUIDs as strings
  and `occurred_at` as ISO 8601. Ingestion ADR 0014 says Phase 3 owns any
  versioning, renaming or formal schema, and that `_as_payload` in the outbox
  publisher is the one function on that side that changes.

**The window for changing that shape for free closes when ingestion's relay
(4.3) ships.** Until then nothing reads the outbox. From then on every change is
a change to something already published.

## Rules specific to this repository

- **Changing an event schema always needs explicit approval**
  (`COLLABORATION.md` §4), with at least one rejected alternative.
- **Defining an event contract is an ADR trigger** (`COLLABORATION.md` §8).
  Every new event, and every breaking change, gets one.
- **Two repositories consume this one.** A change here is not finished until the
  consumers have been considered; say in the proposal which of them it affects.
- **The toolchain is the ingestion service's, and ADR 0006 records every
  difference.** Python 3.14, `uv`, `hatchling`, `ruff`, `mypy --strict`,
  `pytest`, `coverage`, at the versions ingestion locks. Before opening a pull
  request: `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy`,
  `uv run coverage run -m pytest`, `uv run coverage report`. There is no
  integration half, so a local report is the number CI enforces.
- **`ruff format --check .` reads Markdown too**: fenced Python in `docs/` is held
  to the formatter like any source file (ADR 0006).
- **CI builds the wheel and imports every module under `src/` from it**, in an
  isolated environment, because every other check runs against an editable
  install and cannot see a module the build leaves out. A file under `src/` that
  is not importable fails that step.

## Current phase

**Phase 3 is ready to start; no schema exists yet.**

- **The toolchain scaffold is done** (ADR 0006): an empty, installable
  `rag_contracts`, two tests, and CI. **Whether `Lint, types, tests` is a
  required check is set in GitHub's ruleset for `main`, not here.**
- **Ingestion is blocked on this repository.** Its relay, 4.3, reads
  `EXT3 --> U43` in its build plan: it waits on Phase 3 here.
- **This repository is not the gate.** The gate is ingestion's public URL, and
  nothing here moves it. The retrieval repository is not created until that
  gate is passed.

**`docs/EVENT-INVENTORY.md` is where Phase 3 starts.** It describes
`DocumentIngested` as ingestion writes it today, field by field with sources,
lists the seven questions Phase 3 must answer, and names two gaps no repository
owns yet: **the consumer has no way to fetch a document's content**, and
**nothing reports indexing back**, so ingestion's status never leaves `pending`.

**Next: the first schema, `DocumentIngested`, and it starts with a proposal.**
It brings the first runtime dependency: Pydantic, whose range must admit the
2.13.5 ingestion locks. The coverage floor is 100 over a package with no
statements yet; the first schema keeps it or lowers it in a pull request that
says why. The versioning and compatibility policy, and the first tag, are Phase
3's too.

**Keep this section current.** It is the first thing a new session reads, and a
stale one sends the work in the wrong direction.
