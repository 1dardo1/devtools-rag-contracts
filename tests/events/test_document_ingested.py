"""`DocumentIngested` against the payload ingestion writes today.

The first test is the inventory's example, character for character: it is the
shape a consumer will actually receive, so every other test is a variation on a
payload known to be real. ADR 0007.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from rag_contracts.events import EVENT_TYPE, STREAM_NAME, DocumentIngested

_AS_INGESTION_WRITES_IT: dict[str, Any] = {
    "document_id": "2f6b3c1e-6a3e-4c55-9d3f-7b6a1f0e9c42",
    "collection_id": "8d1e0a57-3b8c-4f0f-a2c4-55e1c0b7d913",
    "content_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "occurred_at": "2026-10-28T08:17:34.105557+00:00",
    "metadata": {
        "source_library": "pydantic",
        "doc_type": "how_to",
        "library_version": "2.9",
        "source_url": "https://docs.pydantic.dev/2.9/concepts/models/",
    },
}


def _payload(**changes: Any) -> dict[str, Any]:
    return {**_AS_INGESTION_WRITES_IT, **changes}


def _metadata(**changes: Any) -> dict[str, Any]:
    return _payload(metadata={**_AS_INGESTION_WRITES_IT["metadata"], **changes})


class TestThePayloadIngestionWritesToday:
    def test_it_validates_unchanged(self) -> None:
        event = DocumentIngested.model_validate(_AS_INGESTION_WRITES_IT)

        assert str(event.document_id) == _AS_INGESTION_WRITES_IT["document_id"]
        assert event.metadata.doc_type == "how_to"
        assert event.occurred_at == datetime(
            2026, 10, 28, 8, 17, 34, 105557, tzinfo=UTC
        )

    def test_a_payload_without_a_version_is_version_one(self) -> None:
        # Rows already in ingestion's outbox were written before this contract.
        assert (
            DocumentIngested.model_validate(_AS_INGESTION_WRITES_IT).schema_version == 1
        )

    def test_a_producer_always_writes_the_version(self) -> None:
        dumped = DocumentIngested.model_validate(_AS_INGESTION_WRITES_IT).model_dump(
            mode="json"
        )

        assert dumped["schema_version"] == 1

    def test_it_survives_a_round_trip_through_json(self) -> None:
        event = DocumentIngested.model_validate(_AS_INGESTION_WRITES_IT)

        again = DocumentIngested.model_validate_json(event.model_dump_json())

        assert again == event

    def test_it_is_immutable(self) -> None:
        event = DocumentIngested.model_validate(_AS_INGESTION_WRITES_IT)

        with pytest.raises(ValidationError):
            event.content_hash = "0" * 64


class TestTheTimestamp:
    @pytest.mark.parametrize(
        "written",
        [
            "2026-10-28T08:17:34.105557+00:00",
            "2026-10-28T08:17:34.105557Z",
            "2026-10-28T10:17:34.105557+02:00",
        ],
    )
    def test_every_spelling_of_one_instant_is_that_instant(self, written: str) -> None:
        event = DocumentIngested.model_validate(_payload(occurred_at=written))

        assert event.occurred_at == datetime(
            2026, 10, 28, 8, 17, 34, 105557, tzinfo=UTC
        )

    @pytest.mark.parametrize(
        "written", ["2026-10-28T08:17:34+00:00", "2026-10-28T08:17:34Z"]
    )
    def test_a_missing_fraction_is_accepted(self, written: str) -> None:
        # `datetime.isoformat` drops it when the microseconds are zero.
        event = DocumentIngested.model_validate(_payload(occurred_at=written))

        assert event.occurred_at == datetime(2026, 10, 28, 8, 17, 34, tzinfo=UTC)

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_payload(occurred_at="2026-10-28T08:17:34"))

    def test_it_is_written_in_utc_with_a_z(self) -> None:
        event = DocumentIngested.model_validate(
            _payload(occurred_at="2026-10-28T10:17:34+02:00")
        )

        assert (
            json.loads(event.model_dump_json())["occurred_at"] == "2026-10-28T08:17:34Z"
        )


class TestTheIdentifiersAndTheHash:
    def test_a_document_id_that_is_not_a_uuid_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_payload(document_id="not-a-uuid"))

    def test_a_collection_id_that_is_not_a_uuid_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_payload(collection_id="not-a-uuid"))

    @pytest.mark.parametrize("bad", ["abc", "9F86D081" + "0" * 56, "g" * 64, "0" * 65])
    def test_a_hash_that_is_not_64_lowercase_hex_digits_is_refused(
        self, bad: str
    ) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_payload(content_hash=bad))


class TestTheMetadata:
    def test_absent_optional_fields_are_null_when_written_and_accepted_when_missing(
        self,
    ) -> None:
        written = _metadata(library_version=None, source_url=None)
        missing = _payload(
            metadata={"source_library": "pydantic", "doc_type": "how_to"},
        )

        for payload in (written, missing):
            event = DocumentIngested.model_validate(payload)
            assert event.metadata.library_version is None
            assert event.metadata.source_url is None

    def test_a_blank_source_library_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_metadata(source_library="   "))

    def test_a_blank_library_version_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_metadata(library_version=""))

    def test_a_doc_type_the_consumer_has_never_heard_of_is_accepted(self) -> None:
        # Adding a value is compatible: this is the whole reason it is a string.
        event = DocumentIngested.model_validate(_metadata(doc_type="video_transcript"))

        assert event.metadata.doc_type == "video_transcript"

    @pytest.mark.parametrize("bad", ["HowTo", "how-to", "how to", "", "tutorial2"])
    def test_a_doc_type_that_is_not_lowercase_words_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_metadata(doc_type=bad))

    @pytest.mark.parametrize(
        "unusual",
        [
            # Each of these is accepted by the ingestion domain, whose rule is
            # `urlparse` with an http or https scheme and a host. The contract
            # must never be stricter than its producer: a document the producer
            # stored would be refused at the outbox, and refused again on every
            # attempt. ADR 0007.
            "HTTPS://Docs.Example.com/A",
            "https://example.com/a b",
            "http://exa\tmple.com/x",
            "https://example.com/caf\u00e9",
            "https://example.com/?q=1#frag",
        ],
    )
    def test_a_source_url_the_producer_accepted_is_never_refused(
        self, unusual: str
    ) -> None:
        event = DocumentIngested.model_validate(_metadata(source_url=unusual))

        assert event.metadata.source_url == unusual

    def test_a_blank_source_url_is_refused(self) -> None:
        # Absent is `null`; a blank string is neither absent nor a URL.
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_metadata(source_url="   "))

    def test_a_source_url_is_not_rewritten(self) -> None:
        # A URL type would add the trailing slash; a consumer must see what was sent.
        event = DocumentIngested.model_validate(
            _metadata(source_url="https://docs.example.dev")
        )

        assert event.metadata.source_url == "https://docs.example.dev"


class TestCompatibility:
    def test_a_field_added_later_does_not_break_a_consumer_built_before_it(
        self,
    ) -> None:
        event = DocumentIngested.model_validate(_payload(page_count=12))

        assert not hasattr(event, "page_count")

    def test_a_later_major_version_is_refused_rather_than_misread(self) -> None:
        with pytest.raises(ValidationError):
            DocumentIngested.model_validate(_payload(schema_version=2))


class TestTheNamesOnTheWire:
    def test_the_event_type_is_a_literal_string(self) -> None:
        assert EVENT_TYPE == "DocumentIngested"

    def test_the_stream_name(self) -> None:
        assert STREAM_NAME == "documents.events"
