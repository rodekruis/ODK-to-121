from __future__ import annotations

from odk_to_121.data_provider import DataProvider, LoadedDataSource
from odk_to_121.data_submitter import DataSubmitter
from odk_to_121.data_types.config_types import DataSource
from odk_to_121.data_types.domain_types import (
    FieldMapping,
    OdkSubmission,
    OdkSubmissionSet,
    RegistrationMapping,
)
from odk_to_121.transform import transform_submissions


def _provider(submission_set: OdkSubmissionSet) -> DataProvider:
    """A provider pre-loaded with submissions, so the transform needs no extraction."""
    provider = DataProvider()
    provider.loaded_data[DataSource.DUMMY_SUBMISSIONS] = LoadedDataSource(
        data_source=DataSource.DUMMY_SUBMISSIONS, data=submission_set
    )
    return provider


def _submitter() -> DataSubmitter:
    """An empty submitter with no 121 client; the transform only accumulates into it."""
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
    assert first.preferred_language is None


def test_unanswered_questions_become_none(
    submission_set: OdkSubmissionSet, mapping: RegistrationMapping
) -> None:
    stripped = OdkSubmissionSet(
        project_id=submission_set.project_id,
        form_id=submission_set.form_id,
        submissions=(
            submission_set.submissions[0].__class__(
                instance_id="uuid:9",
                values={"person/fullName": "No household"},
            ),
        ),
    )
    submitter = _submitter()

    transform_submissions(_provider(stripped), submitter, "form-a", mapping)

    assert submitter.registrations[0].attributes["householdSize"] is None
    assert submitter.registrations[0].attributes["phoneNumber"] is None


def test_a_preferred_language_question_sets_the_language_per_person(
    field_mappings: tuple[FieldMapping, ...],
) -> None:
    mapping = RegistrationMapping(
        fields=(
            *field_mappings,
            FieldMapping(odk_field="person/lang", attribute="preferredLanguage", is_built_in=True),
        ),
    )
    submission_set = OdkSubmissionSet(
        project_id=1,
        form_id="registration_form",
        submissions=(
            OdkSubmission(
                instance_id="uuid:1",
                values={"person/fullName": "Answered", "person/lang": "ar"},
            ),
            OdkSubmission(
                instance_id="uuid:2",
                values={"person/fullName": "Skipped", "person/lang": ""},
            ),
        ),
    )
    submitter = _submitter()

    transform_submissions(_provider(submission_set), submitter, "form-a", mapping)

    assert [r.preferred_language for r in submitter.registrations] == ["ar", None]
    # It is a built-in, so it must not also travel as a data attribute.
    assert "preferredLanguage" not in submitter.registrations[0].attributes


def test_an_fsp_configuration_question_sets_the_fsp_per_person(
    field_mappings: tuple[FieldMapping, ...],
) -> None:
    mapping = RegistrationMapping(
        fields=(
            *field_mappings,
            FieldMapping(
                odk_field="person/fsp",
                attribute="programFspConfigurationName",
                is_built_in=True,
            ),
        ),
    )
    submission_set = OdkSubmissionSet(
        project_id=1,
        form_id="registration_form",
        submissions=(
            OdkSubmission(
                instance_id="uuid:1",
                values={"person/fullName": "Answered", "person/fsp": "Airtel"},
            ),
            OdkSubmission(
                instance_id="uuid:2",
                values={"person/fullName": "Skipped", "person/fsp": ""},
            ),
        ),
    )
    submitter = DataSubmitter(
        route_id="form-a",
        program_id=1,
        source_form_id="registration_form",
        default_fsp_configuration_name="Excel",
    )

    transform_submissions(_provider(submission_set), submitter, "form-a", mapping)

    # An unanswered question falls back to the configuration the route resolved.
    assert [r.fsp_configuration_name for r in submitter.registrations] == ["Airtel", "Excel"]
    # It is a built-in, so it must not also travel as a data attribute.
    assert "programFspConfigurationName" not in submitter.registrations[0].attributes


def test_an_unanswered_built_in_is_left_out_but_a_plain_attribute_stays_empty(
    field_mappings: tuple[FieldMapping, ...],
) -> None:
    """121 validates its own columns, so it must not receive an empty one."""
    mapping = RegistrationMapping(
        fields=(
            *field_mappings,
            FieldMapping(odk_field="person/payments", attribute="maxPayments", is_built_in=True),
        ),
    )
    submission_set = OdkSubmissionSet(
        project_id=1,
        form_id="registration_form",
        submissions=(
            OdkSubmission(instance_id="uuid:1", values={"person/fullName": "Skipped"}),
            OdkSubmission(
                instance_id="uuid:2",
                values={"person/fullName": "Answered", "person/payments": 0},
            ),
        ),
    )
    submitter = _submitter()

    transform_submissions(_provider(submission_set), submitter, "form-a", mapping)

    assert "maxPayments" not in submitter.registrations[0].attributes
    assert submitter.registrations[0].attributes["phoneNumber"] is None
    # A falsy answer is still an answer.
    assert submitter.registrations[1].attributes["maxPayments"] == 0


def test_empty_submission_set_produces_no_registrations(mapping: RegistrationMapping) -> None:
    submitter = _submitter()

    transform_submissions(
        _provider(OdkSubmissionSet(project_id=1, form_id="registration_form")),
        submitter,
        "form-a",
        mapping,
    )

    assert submitter.registrations == []
