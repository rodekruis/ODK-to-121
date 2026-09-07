from __future__ import annotations

from odk_to_121.data_types.output_types import Registration


def test_to_dict_carries_answers_and_the_keys_the_pipeline_owns() -> None:
    payload = Registration(
        reference_id="uuid:1",
        attributes={"fullName": "Ada", "householdSize": 4},
        preferred_language="ar",
        fsp_configuration_name="Excel",
    ).to_dict()

    assert payload == {
        "referenceId": "uuid:1",
        "preferredLanguage": "ar",
        "programFspConfigurationName": "Excel",
        "fullName": "Ada",
        "householdSize": 4,
    }


def test_an_answer_cannot_override_a_key_the_pipeline_owns() -> None:
    """A form question named after a built-in would otherwise break idempotence."""
    payload = Registration(
        reference_id="uuid:real",
        attributes={"referenceId": "from-the-form", "programFspConfigurationName": "OtherFsp"},
        fsp_configuration_name="Excel",
    ).to_dict()

    assert payload["referenceId"] == "uuid:real"
    assert payload["programFspConfigurationName"] == "Excel"


def test_unset_optional_keys_are_omitted() -> None:
    payload = Registration(reference_id="uuid:1", attributes={"fullName": "Ada"}).to_dict()

    assert payload == {"referenceId": "uuid:1", "fullName": "Ada"}
