# 2. Split the system into two services and a contracts package

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

The system ingests developer documentation, indexes it as vector embeddings,
and answers questions grounded in it (`ARCHITECTURE.md` §1). Those are two jobs
with little in common beyond the documents they share. This decision was taken
when the system was designed and recorded in `ARCHITECTURE.md` §1, §2 and §5;
this record writes it down where the system's ADRs belong (contracts ADR 0001).

`ARCHITECTURE.md` §2 gives the reason in one paragraph: the two jobs have
**opposing load profiles**. Ingestion "arrives in bursts, tolerates latency,
and is write-heavy against a relational store". Retrieval "must respond in low
single-digit seconds, is read-heavy, and scales with query volume rather than
corpus size".

Splitting into two services raises a second question at once: where the shape
of the messages between them is defined. `ARCHITECTURE.md` §4 principle 6
answers it: **"Event schemas live only in `rag-contracts`. Copying a schema
between services defeats the separation."**

## Options considered

- **One service** that accepts documents, indexes them and serves queries. One
  repository, one deployment, no wire format to agree on. Rejected: a burst of
  ingestion would compete with queries for the same process, and the two
  halves could only be scaled together. `ARCHITECTURE.md` §2 is explicit that
  **"independent deployment and scaling is the justification — not repository
  count"**.
- **Two services, each defining the event in its own code.** No third
  repository. Rejected by principle 6: the producer's and the consumer's
  copies would agree only until one of them changed, and nothing would notice.
- **Two services, with the schema inside the ingestion package**, which the
  retrieval service would install. Rejected as a consequence of the same
  principle: the consumer would depend on the whole producer to read one
  message, and the contract would change whenever the producer's code did.
- **Two services and one contracts package.** Chosen.

## Decision

Three repositories:

- **The ingestion service** (`devtools-rag-ingestion`): FastAPI and PostgreSQL.
  Accepts documents, enforces the domain rules, stores the raw content, and
  announces each accepted document through a transactional outbox. It knows
  nothing about embeddings, chunking or vector stores.
- **The retrieval service**: FastAPI, Qdrant and an LLM. Consumes the
  announcements, chunks, embeds, indexes, and answers queries. Not yet created.
- **The contracts package** (`devtools-rag-contracts`, import root
  `rag_contracts` per ingestion ADR 0003): Pydantic v2 schemas for every
  published event, semantically versioned, consumed by both services as a
  **pinned Git dependency**. It is not a service and holds no infrastructure
  client.

Both services follow the same hexagonal layout (`ARCHITECTURE.md` §4
principles 1 to 4, §6). The build order puts the contracts package at Phase 3,
after the ingestion domain, because "the event shape is derived from the domain
built in Phase 1. Designing it first would be guessing" (`ARCHITECTURE.md` §5).

The ingestion service must be deployed with a public URL and green CI before
the retrieval repository is created — the **hard gate** of `ARCHITECTURE.md` §5
Phase 7.

## Consequences

**Positive.** Each service can be deployed and scaled on its own schedule. The
ingestion domain has been built and tested with no knowledge of AI, which is
the independence the architecture exists to show. The wire format has exactly
one definition, in a repository whose only job is to hold it.

**Negative: every contract change is a change in three repositories.** A schema
edit here is not finished until both consumers have been considered, a new
version tagged, and each service's pin moved. A single service would make the
same change in one pull request.

**Negative: the order of the repositories is now a dependency between them.**
Ingestion is ahead of this package and already writes `DocumentIngested` to its
outbox, so Phase 3 inherits a shape rather than choosing one
(`docs/EVENT-INVENTORY.md`). Meanwhile ingestion's relay (its unit 4.3) cannot
be built until Phase 3 exists, and this repository's own toolchain scaffold,
which Phase 3 needs first, has not been scheduled (ingestion
`OPEN-DECISIONS.md` §6).

**Negative: the split exposes contracts nobody has drawn yet.** The event does
not carry the document's content, and no endpoint returns it, so the consumer
has no way to read what it is told to index. And nothing reports indexing back,
so ingestion's document status never leaves `pending`. Both are recorded as
gaps in `docs/EVENT-INVENTORY.md` §4, and both exist only because the work is
split across a boundary.

**Negative: the gate makes progress visible but serial.** `ARCHITECTURE.md`
accepts that "two half-finished repositories are worth less than one finished
one"; the price is that nothing on the retrieval side, including the
evaluation that §1.1 calls the most valuable part of the system, can start
until ingestion is publicly deployed.
