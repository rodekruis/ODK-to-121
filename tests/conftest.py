from __future__ import annotations

import pytest

from odk_to_121.infra.data_types.domain_types import (
    FieldMapping,
    OdkSubmission,
    OdkSubmissionSet,
    RegistrationMapping,
)
from odk_to_121.infra.utils.dummy_data import DUMMY_SUBMISSION_ROWS


@pytest.fixture
def submission_set() -> OdkSubmissionSet:
    return OdkSubmissionSet(
        project_id=1,
        form_id="registration_form",
        submissions=tuple(OdkSubmission.from_odata(row) for row in DUMMY_SUBMISSION_ROWS),
    )


@pytest.fixture
def field_mappings() -> tuple[FieldMapping, ...]:
    return (
        FieldMapping(odk_field="person/fullName", attribute="fullName", required=True),
        FieldMapping(odk_field="person/phoneNumber", attribute="phoneNumber", required=True),
        FieldMapping(odk_field="household/householdSize", attribute="householdSize"),
    )


@pytest.fixture
def mapping(field_mappings: tuple[FieldMapping, ...]) -> RegistrationMapping:
    return RegistrationMapping(
        program_id=1,
        reference_id_field="__id",
        fields=field_mappings,
        preferred_language="en",
    )
