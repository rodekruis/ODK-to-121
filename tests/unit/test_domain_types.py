from __future__ import annotations

from datetime import UTC, datetime

from odk_to_121.infra.data_types.domain_types import OdkSubmission


def test_from_odata_flattens_groups_and_parses_system_fields() -> None:
    submission = OdkSubmission.from_odata(
        {
            "__id": "uuid:1",
            "__system": {"submissionDate": "2026-01-15T09:30:00.000Z", "reviewState": "approved"},
            "person": {"full_name": "Ada", "contact": {"phone": "3160"}},
            "consent": True,
        }
    )

    assert submission.instance_id == "uuid:1"
    assert submission.submission_date == datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    assert submission.review_state == "approved"
    assert submission.values == {
        "person/full_name": "Ada",
        "person/contact/phone": "3160",
        "consent": True,
    }


def test_get_reads_instance_id_and_nested_paths() -> None:
    submission = OdkSubmission.from_odata(
        {"__id": "uuid:2", "person": {"full_name": "Grace"}},
    )

    assert submission.get("__id") == "uuid:2"
    assert submission.get("person/full_name") == "Grace"
    assert submission.get("person/missing") is None


def test_from_odata_rejects_submission_without_instance_id() -> None:
    try:
        OdkSubmission.from_odata({"person": {"full_name": "No id"}})
    except ValueError as exc:
        assert "__id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
