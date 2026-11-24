# 7. The `DocumentIngested` contract

- **Status:** Accepted
- **Last revised:** 2026-11-24

## Context

`DocumentIngested` is the one event the system publishes, and ingestion already
writes it to its outbox. **Nothing has read those rows yet**: the relay, ingestion
4.3, does not exist. That is the last moment at which any answer below costs
nothing, because from the first published entry on, each one changes something
already on the wire.

`docs/EVENT-INVENTORY.md` §3 lists seven questions. This record answers them, and
the schema in `src/rag_contracts/events/document_ingested.py` is the answer in
code. It covers the event's *shape*. It does not cover the compatibility policy
and the first release tag, which follow in their own pull request, nor the two
gaps of inventory §4 (the consumer cannot fetch content; nothing reports indexing
back), which each need a proposal of their own.

## Options considered

### 1. Where the version travels

- **`schema_version: 1`, an integer inside the payload.** Chosen. The payload is
  stored as `jsonb` and outlives any one stream entry, so a row read from the
  database years later still says which schema it follows. Absent means 1: the
  rows ingestion wrote before this record carry no version, and they are version 1.
- **A new column on the outbox.** Rejected: a migration in ingestion, and the
  relay would have to know about the schema in order to copy it.
- **The version in the stream's name** (`documents.events.v1`). Rejected: every
  breaking change would split consumers across two streams, and replays of
  at-least-once delivery could straddle them.

### 2. The shape of a stream entry

- **Two flat fields: `event_type` and `payload`, the payload being JSON text.**
  Chosen. A Redis Streams entry is a flat map of strings, and ingestion ADR 0014
  wants the relay to stay a dumb pipe: it copies two columns of the outbox row and
  interprets neither.
- **Flattening the payload into one field per key.** Rejected: the relay would
  need the schema, and the nested `metadata` would have to be flattened and
  rebuilt.

### 3. The stream's name

- **One stream, `documents.events`, with `event_type` telling events apart.**
  Chosen.
- **One stream per event type.** Rejected: more consumer groups and no ordering
  across types, in exchange for nothing while there is a single event.

### 4. Where `event_type` and the version sit

- **`event_type` outside the payload, the version inside.** Chosen. `event_type`
  is already an outbox column and a stream field, and is a literal string, never
  derived from a class name, so that renaming a class cannot rename an event.
- **Both inside the payload.** Rejected: it would duplicate a constant that is
  already a column.

### 5. The timestamp

- **`AwareDatetime`, normalised to UTC when validated.** Chosen. The contract is
  RFC 3339 with an offset and an optional fraction, and a consumer parses it with
  a parser, never a fixed pattern: `datetime.isoformat` drops the fraction when the
  microseconds are zero, which a fixed pattern would meet about once in a million
  events. The normalisation is not decoration. A first version of the tests showed
  that Pydantic writes back whatever offset it was given, so one instant had as
  many spellings as there were offsets; now it is always `…Z`.
- **An integer count of microseconds.** Rejected: unreadable in a log, and it
  solves nothing a parser does not.

### 6. Field names

- **The ingestion domain's names, unchanged.** Chosen: `document_id`,
  `collection_id`, `content_hash`, `metadata`, `occurred_at`.
- **Renaming for the wire.** Rejected: a translation to maintain in
  `_as_payload`, for no gain to either consumer.

### 7. Who validates

- **Both.** Chosen. The producer builds the model before it writes to the outbox,
  so an invalid event is never persisted; the consumer validates what it reads.
- **Only the consumer.** Rejected: a malformed event would sit in the outbox, and
  the relay would republish it for ever.

### Is adding a `doc_type` value a breaking change?

- **No: on the wire `doc_type` is a string matching `^[a-z_]+$`.** Chosen. The
  ingestion domain keeps its own closed set of 25 values and validates against it,
  so nothing unknown is ever *stored*. What the contract refuses to do is let a
  new value stop a consumer built before it existed.
- **A closed `Literal` of the 25 values.** Rejected: each new value would force
  the consumer to deploy before the producer, which is lockstep with extra steps.

## Decision

- The model is `rag_contracts.events.DocumentIngested`, with `DocumentMetadata`
  nested in it. Both are immutable and **ignore unknown fields**, so a field added
  later does not break a consumer built before it.
- `schema_version` is `Literal[1]`. A payload from a later major version fails
  validation instead of being read as the one this consumer understands.
- **Compatible** changes, with no new `schema_version`: adding an optional field
  with a default, and adding a `doc_type` value. **Incompatible** ones, which bump
  it: removing or renaming a field, changing a type, or making an optional field
  required.
- **The contract is never stricter than its producer.** `source_library`,
  `library_version` and `source_url` are non-blank text, stripped, and nothing
  more. Whether a `source_url` is a usable URL is the ingestion domain's rule
  (`urlparse`, an http or https scheme, a host), applied before anything is
  stored. The first version of this schema carried a pattern of its own for
  `source_url`, and ingestion's review showed it refusing three things the domain
  accepts: an upper-case scheme (`HTTPS://…`), whitespace inside the URL, and a
  tab. Each would have been a document stored and then refused at the outbox,
  every time, as a 500. `source_url` is also not `AnyUrl`, because Pydantic's URL
  types normalise (a bare host gains a trailing slash) and a value would change
  on its way through the contract.
- `EVENT_TYPE` (`"DocumentIngested"`) and `STREAM_NAME` (`"documents.events"`) are
  constants of this package, because a name on the wire is as much a part of the
  contract as a field.
- Pydantic is the package's first dependency, `>=2.13.5,<3`. 2.13.5 is what
  ingestion locks.

## Consequences

**Positive: the contract is checked against the payload ingestion really writes.**
The first test is the inventory's example, character for character, and a second
shows that a payload with no version, which is what the rows already in ingestion's
outbox look like, validates as version 1.

**Negative: a consumer can no longer assume `source_url` is a URL.** It receives
whatever the producer's rule let through, including values a browser would not
open. A consumer that needs a URL parses and handles failure itself, and that is
the price of the rule above.

**Negative: two definitions of the metadata rules now exist** — the ingestion
domain's and this package's. They agree today. Nothing makes them keep agreeing
except a test in ingestion that passes the real outbox payload through this model,
which is the next pull request and is not here.

**Negative: a consumer cannot be exhaustive over `doc_type`.** A `match` with no
default case is a bug waiting for the first new value. The cost of an open field is
that the type system cannot catch it.

**Negative: ignoring unknown fields means a typo is silent.** A producer that
misspells an optional field produces a valid event with the field missing. The
producer-side model, built before the outbox write, is where a misspelling in the
*producer's* code would show up as a missing required field, but not for an
optional one.

**Negative: `Literal[1]` is a wall.** When version 2 exists, a consumer that has
not been updated refuses its events outright. That is the point, and it also means
a breaking change is a coordinated deployment, which the policy has to say.

**Negative: Pydantic's behaviour is now part of the contract.** Which spellings of
a timestamp are accepted, and how a UUID is written, are Pydantic 2's. The range
admits 2.13.5 to below 3, and the tests pin the behaviour that matters.
