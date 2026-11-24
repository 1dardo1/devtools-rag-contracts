"""`DocumentIngested`: a document has been accepted, stored and committed.

Published once per accepted document by the ingestion service and consumed by
the retrieval service. It does **not** carry the content: a consumer fetches the
bytes by `document_id`. Delivery is at-least-once and unordered, so a consumer
must be idempotent, and `document_id` is what recognises a repeat -- never
`content_hash` alone, which two different documents can share.

The model describes the *payload*. `event_type` travels beside it, as its own
field of the stream entry, and is not part of it. ADR 0007 records why each
choice below was made.
"""

from datetime import UTC
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
)

# A constant, never derived from the class name: renaming a class must not
# rename an event on the wire.
EVENT_TYPE: Final = "DocumentIngested"

_NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DocumentMetadata(BaseModel):
    """What describes a document, as the ingestion domain carries it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    source_library: _NonBlank
    # A string, not a closed enum. The ingestion domain keeps its own closed set
    # of values; on the wire a new one must not stop a consumer that has not
    # heard of it, so adding one is compatible. A consumer must never branch
    # exhaustively on this field. ADR 0007.
    doc_type: Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]
    # Free text, not a parsed version: "2.9" and "0.141.1" are both legitimate.
    library_version: _NonBlank | None = None
    # Text, and no more than text. Whether it is a *usable* URL is the producer's
    # judgement, made before the document is stored; a consumer only carries it.
    # A pattern here would be stricter than the producer's own rule, and a
    # document the producer accepted would then be refused at the outbox, over
    # and over. Not `AnyUrl` either: Pydantic's URL types normalise (a bare host
    # gains a trailing slash), so a value would change on its way through. ADR 0007.
    source_url: _NonBlank | None = None


class DocumentIngested(BaseModel):
    """The payload of a `DocumentIngested` event."""

    # Unknown fields are ignored so that a compatible addition, a new optional
    # field, does not break a consumer built before it existed.
    model_config = ConfigDict(frozen=True, extra="ignore")

    # Absent means 1: the payloads ingestion wrote before this contract existed
    # carry no version, and they are version 1. A producer always writes it.
    schema_version: Literal[1] = 1
    document_id: UUID
    collection_id: UUID
    # SHA-256 of the *decoded* content, as 64 lowercase hex digits.
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    # The instant ingestion accepted the document, never of publication. On the
    # wire: RFC 3339 with an offset, fraction optional -- Python's `isoformat`
    # drops the fraction at zero microseconds, so a parser must not assume it.
    # Normalised to UTC on the way in, because Pydantic otherwise writes back
    # whatever offset it was given, and one instant would have many spellings.
    occurred_at: Annotated[
        AwareDatetime, AfterValidator(lambda moment: moment.astimezone(UTC))
    ]
    metadata: DocumentMetadata


__all__ = ["EVENT_TYPE", "DocumentIngested", "DocumentMetadata"]
