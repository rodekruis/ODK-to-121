from __future__ import annotations

from odk_to_121.data_types.domain_types import OdkSubmission


def test_from_odata_flattens_groups_and_drops_system_keys() -> None:
    submission = OdkSubmission.from_odata(
        {
            "__id": "uuid:1",
            "__system": {"submissionDate": "2026-01-15T09:30:00.000Z", "reviewState": "approved"},
            "person": {"full_name": "Ada", "contact": {"phone": "3160"}},
            "consent": True,
        }
    )

    assert submission.instance_id == "uuid:1"
    assert submission.values == {
        "person/full_name": "Ada",
        "person/contact/phone": "3160",
        "consent": True,
    }


def test_get_reads_nested_paths() -> None:
    submission = OdkSubmission.from_odata(
        {"__id": "uuid:2", "person": {"full_name": "Grace"}},
    )

    assert submission.instance_id == "uuid:2"
    assert submission.get("person/full_name") == "Grace"
    assert submission.get("person/missing") is None


def test_from_odata_rejects_submission_without_instance_id() -> None:
    try:
        OdkSubmission.from_odata({"person": {"full_name": "No id"}})
    except ValueError as exc:
        assert "__id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
