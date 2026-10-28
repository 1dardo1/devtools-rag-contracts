# 3. The services communicate through events and a transactional outbox

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

Contracts ADR 0002 splits the system into an ingestion service and a retrieval
service. Every accepted document has to reach the retrieval service to be
indexed, so the two must communicate, and how they do so decides what happens
when one of them is down. This decision was taken when the system was designed
and recorded in `ARCHITECTURE.md` §2 ("Why events and not a direct HTTP call")
and §5 Phase 4; this record writes it down where the system's ADRs belong.

Unlike the broker (contracts ADR 0004), much of this decision is already built.
The ingestion service writes the outbox row in the document's own transaction
(ingestion ADRs 0012, 0013, 0014 and 0017), and an integration test,
`TestTheDocumentAndItsOutboxRowAreAtomic`, proves it through the real use case.
**The relay that publishes those rows does not exist yet** (ingestion unit
4.3), so nothing has ever been delivered.

## Options considered

- **A direct HTTP call** from ingestion to retrieval when a document is
  accepted. The simplest thing that could work, with no broker and no relay.
  Rejected, in `ARCHITECTURE.md` §2's words: "a synchronous call would couple
  availability: if the indexer is down, ingestion fails."
- **Events, published to the broker from inside the request.** Decoupled in
  time, and no relay to run. Rejected: it is a write to two systems that no one
  transaction can span. Ingestion ADR 0014 puts it most directly — **"a socket
  cannot be rolled back"** — so a document could be stored with its event lost,
  or announced and then rolled back.
- **Events, written to an outbox table in the document's transaction and
  published later by a separate relay.** Chosen.

## Decision

**Work crosses the boundary only as published events.** Ingestion never calls
the retrieval service to tell it about a document. How the consumer then reads
the document's content is a separate question, still open: the event leaves the
bytes out, and nothing serves them yet (`docs/EVENT-INVENTORY.md` §4.1).

**The producer writes the event to an outbox in the same database transaction
as the change it announces.** For ingestion that is the document row and its
`outbox` row, on one connection, committed once (ingestion ADRs 0013, 0014,
0017). A committed document always has its row; a rolled-back one never does.

**A separate relay process publishes outbox rows to the broker and marks them
sent.** It does not share a lifecycle with the API process (`ARCHITECTURE.md`
§2), and it is a dumb pipe: it reads a row, sends its payload, and marks it,
without shaping the message (ingestion ADR 0014). The schema of what it sends
lives only in this repository (`ARCHITECTURE.md` §4 principle 6).

**Delivery is at-least-once, and the consumer must be idempotent**
(`ARCHITECTURE.md` §4 principle 7): reprocessing an event must not duplicate
chunks or corrupt the index.

## Consequences

**Positive.** Ingestion keeps accepting documents while the broker or the
retrieval service is down; the outbox simply grows and drains later. No event
is lost once its document is committed, and that is a property of one database
transaction, not of any network.

**Negative: duplicates are normal, not exceptional.** A relay that publishes
and then crashes before marking the row sends it again. The retrieval consumer
has to recognise a repeat, and `docs/EVENT-INVENTORY.md` §2 records what it can
rely on: `document_id` identifies the document, while `content_hash` alone does
not, because ingestion deduplicates per collection and excludes failed
documents.

**Negative: there is no global order.** Outbox identity values are assigned at
insert, not at commit, so a lower `outbox_id` can commit after a higher one and
be published later (ingestion ADR 0012). No consumer may assume an order.

**Negative: the event is late by an unbounded amount.** A second, or twenty
minutes if the broker was down. That is why `occurred_at` is the instant of
ingestion and never of publication (ingestion ADR 0009), and it means the
retrieval index is always eventually, never immediately, consistent with what
ingestion has accepted.

**Negative: the invariant is only as strong as the wiring, and no type protects
it.** A document repository and an outbox publisher on two different
connections typecheck and are not atomic (ingestion ADR 0014). It is held by an
integration test of the composition, not by the design alone.

**Negative: a third process has to be run and watched.** The relay runs
unattended, and a crashed relay and an idle one both write nothing; making that
silence legible is an open decision due before 4.3 (ingestion `BUILD-PLAN.md`).
It also does not fit the free plan the ingestion API is deployed on, so 4.3
reopens the hosting question (ingestion ADR 0025).

**Negative: events flow one way.** Nothing carries indexing results back to
ingestion, so its document status stays `pending` (`docs/EVENT-INVENTORY.md`
§4.2). Closing that would make ingestion a consumer too, and is not decided.
