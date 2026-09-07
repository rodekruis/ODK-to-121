from __future__ import annotations

import pytest

from odk_to_121.data_types.domain_types import OdkFormField, OdkFormSchema
from odk_to_121.data_types.output_types import AttributeType
from odk_to_121.schema_sync import (
    BUILT_IN_ATTRIBUTES,
    FORBIDDEN_ATTRIBUTES,
    derive_schema_plan,
)


def _schema(*fields: tuple[str, str, str]) -> OdkFormSchema:
    """Build a form schema from (path, name, type) triples."""
    return OdkFormSchema(
        project_id=1,
        form_id="registration_form",
        fields=tuple(
            OdkFormField(name=name, path=path, type=field_type) for path, name, field_type in fields
        ),
    )


def test_maps_field_types_and_keys_attributes_on_the_leaf_name() -> None:
    schema = _schema(
        ("person", "person", "structure"),
        ("person/fullName", "fullName", "string"),
        ("household/householdSize", "householdSize", "int"),
        ("household/income", "income", "decimal"),
        ("visitedOn", "visitedOn", "date"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert {m.odk_field: m.attribute for m in plan.mappings} == {
        "person/fullName": "fullName",
        "household/householdSize": "householdSize",
        "household/income": "income",
        "visitedOn": "visitedOn",
    }
    assert {a.name: a.type for a in plan.attributes} == {
        "fullName": AttributeType.TEXT,
        "householdSize": AttributeType.NUMERIC,
        "income": AttributeType.NUMERIC,
        # 121 stores dates as text because its date type rejects ODK's formats.
        "visitedOn": AttributeType.TEXT,
    }


def test_skips_metadata_groups_and_attachments() -> None:
    schema = _schema(
        ("person/fullName", "fullName", "string"),
        ("meta", "meta", "structure"),
        ("meta/instanceID", "instanceID", "string"),
        ("start", "start", "dateTime"),
        ("deviceid", "deviceid", "string"),
        ("photo", "photo", "binary"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert [a.name for a in plan.attributes] == ["fullName"]


def test_skips_everything_under_a_meta_group() -> None:
    schema = _schema(
        ("person/fullName", "fullName", "string"),
        ("meta", "meta", "structure"),
        ("meta/audit", "audit", "string"),
        ("meta/custom_tracker", "custom_tracker", "string"),
        ("metadata/enumeratorDevice", "enumeratorDevice", "string"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert [a.name for a in plan.attributes] == ["fullName"]


@pytest.mark.parametrize(
    "name",
    ["meta_deviceid", "meta_starttime", "meta_endtime", "meta_today", "metadata-username"],
)
def test_skips_metadata_flattened_onto_the_question_name(name: str) -> None:
    schema = _schema(("person/fullName", "fullName", "string"), (name, name, "string"))

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert [a.name for a in plan.attributes] == ["fullName"]


def test_a_meta_prefix_alone_does_not_drop_a_real_question() -> None:
    schema = _schema(("household/meta_roof_type", "meta_roof_type", "string"))

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert [a.name for a in plan.attributes] == ["meta_roof_type"]


def test_phone_number_is_kept_despite_the_odk_metadata_of_the_same_name() -> None:
    schema = _schema(
        ("person/phoneNumber", "phoneNumber", "string"),
        ("meta/phonenumber", "phonenumber", "string"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert [a.name for a in plan.attributes] == ["phoneNumber"]


@pytest.mark.parametrize("name", sorted(BUILT_IN_ATTRIBUTES))
def test_built_in_attributes_are_mapped_but_never_created(name: str) -> None:
    schema = _schema(
        ("person/fullName", "fullName", "string"),
        (name, name, "string"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert errors == []
    assert name in {m.attribute for m in plan.mappings}
    assert name not in {a.name for a in plan.attributes}


@pytest.mark.parametrize("name", sorted(FORBIDDEN_ATTRIBUTES))
def test_a_field_named_after_a_121_generated_attribute_is_an_error(name: str) -> None:
    schema = _schema(
        ("person/fullName", "fullName", "string"),
        (f"person/{name}", name, "string"),
    )

    plan, errors = derive_schema_plan("form-a", schema)

    assert len(errors) == 1
    assert name in errors[0]
    assert "sets itself" in errors[0]
    # Only the offending field is dropped; the rest of the form still maps.
    assert [a.name for a in plan.attributes] == ["fullName"]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ((("roster", "roster", "repeat"),), "cannot store"),
        (
            (("a/size", "size", "int"), ("b/size", "size", "int")),
            "both map to attribute 'size'",
        ),
    ],
)
def test_reports_unusable_forms(fields: tuple[tuple[str, str, str], ...], expected: str) -> None:
    plan, errors = derive_schema_plan("form-a", _schema(*fields))

    assert len(errors) == 1
    assert expected in errors[0]
    assert plan.attributes == () or "size" in {a.name for a in plan.attributes}


def test_form_without_usable_fields_is_an_error() -> None:
    _, errors = derive_schema_plan("form-a", _schema(("meta", "meta", "structure")))

    assert len(errors) == 1
    assert "no usable fields" in errors[0]
