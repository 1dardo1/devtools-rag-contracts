# 5. The corpus: developer documentation for the system's own stack

- **Status:** Accepted
- **Last revised:** 2026-10-28

## Context

A retrieval system is built over some body of documents, and that choice
reaches further than it looks: it decides what questions the system can be
evaluated on, what metadata travels with each document, and how documents may
be cut into chunks. This decision was taken when the system was designed and
recorded in `ARCHITECTURE.md` §1.1; this record writes it down where the
system's ADRs belong. The ingestion repository's `README.md`, `CLAUDE.md` and
`ARCHITECTURE.md` already cite it as "ADR 0005 in the contracts repository".

It is system-wide because it binds both services: the ingestion domain carries
its metadata, the retrieval service chunks and evaluates against it, and the
event between them carries the metadata across.

## Options considered

- **A corpus the author does not know well.** Rejected: Phase 11 depends on
  writing question–answer pairs with known-correct answers and judging when the
  system is wrong. **"A corpus the author cannot verify makes evaluation
  impossible, and evaluation is the most valuable part of the system"**
  (`ARCHITECTURE.md` §1.1).
- **A corpus that base models already answer well.** Rejected by the second
  reason below: if the ungrounded model is already right, grounding has
  nothing to be measured against.
- **Shaping the domain around the corpus** — entities or rules that know about
  libraries, versions or APIs. Rejected outright: "if a proposal claims the
  corpus requires a change to `domain/` beyond the metadata fields listed
  above, that proposal is wrong" (`ARCHITECTURE.md` §1.1).
- **The documentation of the system's own stack**: FastAPI, Pydantic v2,
  Qdrant, `uv`, Redis Streams and pytest. Chosen.

## Decision

The system indexes developer documentation for FastAPI, Pydantic v2, Qdrant,
`uv`, Redis Streams and pytest, for three reasons (`ARCHITECTURE.md` §1.1):

- **Evaluation requires familiarity.** The author can tell a right answer from
  a wrong one.
- **It provides a measurable baseline.** Base models reliably confuse Pydantic
  v1 and v2 APIs, and `uv` post-dates most training cutoffs, so
  version-sensitive questions are ones the ungrounded model measurably fails —
  which "turns 'grounding works' from an assertion into a number".
- **It is useful during development.** The corpus gets used while building the
  thing that indexes it.

### What it affects

Exactly three things. The metadata fields are the one place the corpus reaches
ingestion's domain; the other two belong to the retrieval service.

| Affected | How | Where |
|---|---|---|
| Metadata fields | `source_library`, `library_version`, `doc_type`, `source_url` | Ingestion's `Metadata`, and the `DocumentIngested` payload |
| Chunking | **Fenced code blocks must never be split.** A truncated example is worse than no example. | The retrieval service, Phase 9 |
| Evaluation dataset | Question–answer pairs about these libraries, including version-sensitive cases | The retrieval service, Phase 11 |

### What it does not affect

**The domain model**, beyond those four fields. Documents and collections are
the domain whatever their subject. Entities, deduplication, the state machine,
the outbox and every port are identical for any corpus, and that independence
is what the architecture sets out to demonstrate. Ingestion's `CLAUDE.md` restates it for that service:
the corpus affects the metadata fields and nothing else there.

## Consequences

**Positive.** Evaluation is possible, and it has a baseline worth beating.
Every other part of the system stays corpus-agnostic, so swapping the corpus
would change metadata, a chunking rule and a dataset, not the design.

**Negative: nobody has scheduled collecting it.** The roadmap decided *what*
the documents are and never scheduled *gathering* them, and the retrieval
service's evaluation phase cannot happen without them (ingestion
`OPEN-DECISIONS.md` §6 and `BUILD-PLAN.md`). As of this record the corpus is a
decision, not a dataset.

**Negative: the metadata is part of the wire contract.** The four fields travel
in `DocumentIngested`, and `doc_type` is a closed set of 25 values, so adding a
documentation kind is a domain change in ingestion and may be a breaking change
for a consumer that validates against the set (`docs/EVENT-INVENTORY.md` §1.3,
§3.1). `library_version` is free text, not a parsed version, so the
version-sensitive cases this corpus was chosen for cannot rely on comparing it.

**Negative: the baseline erodes.** The second reason rests on models getting
these libraries wrong today. As training cutoffs move past `uv` and Pydantic
v2, that gap is expected to narrow, and the version-sensitive cases will need
to follow newer releases to stay measurable.

**Negative: the chunking rule constrains a service that does not exist.** "Never
split a fenced code block" is fixed here before any chunker is designed, and
it may cost chunk-size uniformity when an example is long. That trade-off
belongs to the retrieval service's own chunking ADR.
