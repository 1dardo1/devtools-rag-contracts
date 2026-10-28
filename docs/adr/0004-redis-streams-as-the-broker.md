# 4. Redis Streams as the broker

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

Contracts ADR 0003 has the services communicate through events, written to an
outbox and published by a relay. The relay needs somewhere to publish them, and
the retrieval service needs somewhere to consume them from. This decision was
taken when the system was designed and recorded in `ARCHITECTURE.md` §2 ("Why
Redis Streams") and §3; this record writes it down where the system's ADRs
belong. `ARCHITECTURE.md` itself says **"this decision belongs in an ADR"**, and
principle 9 lists "broker choice" among the decisions that need one.

**The source reasoning is short, and this record does not lengthen it.**
`ARCHITECTURE.md` §2 gives three reasons for Redis Streams and names one
alternative. Nothing more was compared, and nothing has yet run against Redis:
the relay (ingestion unit 4.3) is not written, and the compose stack leaves
Redis out until it is, because "a Redis nothing reads from would pass its
health check while making the outbox look drained" (ingestion ADR 0021).

## Options considered

- **RabbitMQ.** A dedicated message broker. `ARCHITECTURE.md` §2 names it as
  "the choice if complex routing or dead-letter topologies were required".
  Rejected because neither is required: there is one event type, one producer
  and one consumer.
- **Leave the broker open until the relay is built.** Rejected: Phase 3 has to
  decide what a stream entry looks like and what the stream is called
  (`docs/EVENT-INVENTORY.md` §3, questions 2 and 3), and those answers depend
  on the broker's data model.
- **Redis Streams.** Chosen, for the three reasons `ARCHITECTURE.md` §2 gives:
  **sufficient throughput for this workload, a minimal local footprint, and
  consumer groups built in.**

## Decision

The relay publishes outbox rows to **Redis Streams**, and the retrieval service
consumes them through a **consumer group** (`ARCHITECTURE.md` §2, §5 Phase 9).

What this decision does **not** settle, and leaves to Phase 3 here:

- **The shape of a stream entry.** An entry is a flat map of strings, so the
  payload either travels as one JSON field or is flattened into several. The
  relay should stay a dumb pipe (ingestion ADR 0014), which favours the first,
  but it is not decided (`docs/EVENT-INVENTORY.md` §3.2).
- **The stream name**, and whether there is one stream per event type or one
  for everything (§3.3).
- **Where `event_type` and the schema version travel**, inside the payload or
  beside it in the entry (§3.4).

**The broker carries announcements, never content.** `DocumentIngested` leaves
the document's bytes out on purpose; pushing up to 5 MiB per document through
Redis would make it a content store (`docs/EVENT-INVENTORY.md` §1.5).

## Consequences

**Positive.** One small dependency gives both halves what they need: an
append-only log the relay can write to, and consumer groups the retrieval
service can read from with acknowledgements. Running it locally is one more
container in the compose stack.

**Negative: the guarantees come from the outbox, not from Redis.** At-least-once
delivery and the absence of loss are properties of the outbox and the relay
(contracts ADR 0003, `docs/EVENT-INVENTORY.md` §2). A stream orders entries by
when the relay appended them, which is not the order documents were ingested
(ingestion ADR 0012), and Redis adds no exactly-once promise. A consumer may
lean on neither.

**Negative: no dead-letter handling comes with it.** `ARCHITECTURE.md` names
dead-letter topologies as the reason to pick RabbitMQ instead. If the retrieval
consumer needs somewhere to put an event it cannot process, that is built by
hand on top of streams, or this decision is revisited.

**Negative: the choice is unexercised.** No message has been published, and
the three reasons above are expectations rather than measurements. The first
evidence for or against them arrives with ingestion unit 4.3.

**Negative: Redis has to be hosted somewhere, and nowhere is chosen.** The
ingestion API runs on Render's free web service, which the relay will not fit
(ingestion ADR 0025); the broker it publishes to is a further piece of
infrastructure that the public deployment does not yet include.
