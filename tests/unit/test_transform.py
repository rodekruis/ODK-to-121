from __future__ import annotations

from odk_to_121.infra.data_provider import DataProvider, LoadedDataSource
from odk_to_121.infra.data_submitter import DataSubmitter
from odk_to_121.infra.data_types.config_types import DataSource
from odk_to_121.infra.data_types.domain_types import OdkSubmissionSet, RegistrationMapping
from odk_to_121.transform import transform_submissions


def _provider(submission_set: OdkSubmissionSet) -> DataProvider:
    provider = DataProvider()
    provider.loaded_data[DataSource.DUMMY_SUBMISSIONS] = LoadedDataSource(
        data_source=DataSource.DUMMY_SUBMISSIONS, data=submission_set
    )
    return provider


def _submitter() -> DataSubmitter:
    return DataSubmitter(route_id="form-a", program_id=1, source_form_id="registration_form")


def test_maps_submissions_to_registrations(
    submission_set: OdkSubmissionSet, mapping: RegistrationMapping
) -> None:
    submitter = _submitter()

    transform_submissions(_provider(submission_set), submitter, "form-a", mapping)

    assert [r.reference_id for r in submitter.registrations] == [
        "uuid:00000000-0000-0000-0000-000000000001",
        "uuid:00000000-0000-0000-0000-000000000002",
        "uuid:00000000-0000-0000-0000-000000000003",
    ]
    first = submitter.registrations[0]
    assert first.attributes == {
        "fullName": "Ada Lovelace",
        "phoneNumber": "31600000001",
        "householdSize": 4,
    }
    assert first.preferred_language == "en"


def test_unanswered_questions_become_none(
    submission_set: OdkSubmissionSet, mapping: RegistrationMapping
) -> None:
    stripped = OdkSubmissionSet(
        project_id=submission_set.project_id,
        form_id=submission_set.form_id,
        submissions=(
            submission_set.submissions[0].__class__(
                instance_id="uuid:9",
                submission_date=None,
                review_state=None,
                values={"person/fullName": "No household"},
            ),
        ),
    )
    submitter = _submitter()

    transform_submissions(_provider(stripped), submitter, "form-a", mapping)

    assert submitter.registrations[0].attributes["householdSize"] is None
    assert submitter.registrations[0].attributes["phoneNumber"] is None


def test_empty_submission_set_produces_no_registrations(mapping: RegistrationMapping) -> None:
    submitter = _submitter()

    transform_submissions(
        _provider(OdkSubmissionSet(project_id=1, form_id="registration_form")),
        submitter,
        "form-a",
        mapping,
    )

    assert submitter.registrations == []
