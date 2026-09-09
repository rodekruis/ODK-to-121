from __future__ import annotations

import pytest

from odk_to_121.data_types.domain_types import (
    FieldMapping,
    OdkSubmission,
    OdkSubmissionSet,
    RegistrationMapping,
)
from odk_to_121.utils.dummy_data import DUMMY_SUBMISSION_ROWS


@pytest.fixture
def submission_set() -> OdkSubmissionSet:
    """The dummy submissions, parsed exactly as the ODK OData feed would deliver them."""
    return OdkSubmissionSet(
        project_id=1,
        form_id="registration_form",
        submissions=tuple(OdkSubmission.from_odata(row) for row in DUMMY_SUBMISSION_ROWS),
    )


@pytest.fixture
def field_mappings() -> tuple[FieldMapping, ...]:
    """The ODK-field-to-121-attribute mappings the dummy form implies."""
    return (
        FieldMapping(odk_field="person/fullName", attribute="fullName"),
        FieldMapping(odk_field="person/phoneNumber", attribute="phoneNumber"),
        FieldMapping(odk_field="household/householdSize", attribute="householdSize"),
    )


@pytest.fixture
def mapping(field_mappings: tuple[FieldMapping, ...]) -> RegistrationMapping:
    """The full mapping contract a transform is normally handed by the orchestrator."""
    return RegistrationMapping(
        fields=field_mappings,
    )
