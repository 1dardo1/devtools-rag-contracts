"""The events the services publish, and the stream they travel on. ADR 0007."""

from rag_contracts.events.document_ingested import EVENT_TYPE, DocumentIngested

# One stream for every event, told apart by the entry's `event_type` field. A
# name is a wire fact like a field name, so it lives here and not in a service.
STREAM_NAME = "documents.events"

__all__ = ["EVENT_TYPE", "STREAM_NAME", "DocumentIngested"]
