"""Derive 121 registration attributes from the ODK form and create the missing ones.

Runs before any registration is submitted, because 121 rejects attributes the program
does not know about. Additive only: attributes dropped from the ODK form are left alone,
so the data already collected against them survives.

The type mapping and the reserved-name rules mirror the 121 platform's own Kobo
integration (`services/121-service/src/kobo`), so both integrations produce the same
shape of program.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from odk_to_121.infra.data_types.config_types import RouteConfig
from odk_to_121.infra.data_types.domain_types import FieldMapping, OdkFormField, OdkFormSchema
from odk_to_121.infra.data_types.output_types import AttributeType, ProgramAttribute
from odk_to_121.infra.utils.client_121 import Client121
from odk_to_121.infra.utils.client_odk import ClientOdk
from odk_to_121.infra.utils.extract import extract_form_schema
from odk_to_121.infra.utils.progress import with_progress

logger = logging.getLogger(__name__)

# ODK XForms field type -> 121 attribute type. Dates and geo values become text because
# 121's typed attributes reject the formats ODK produces; 121 does the same for Kobo.
ODK_TYPE_TO_ATTRIBUTE_TYPE: dict[str, AttributeType] = {
    "int": AttributeType.NUMERIC,
    "decimal": AttributeType.NUMERIC,
    "string": AttributeType.TEXT,
    "date": AttributeType.TEXT,
    "time": AttributeType.TEXT,
    "dateTime": AttributeType.TEXT,
    "geopoint": AttributeType.TEXT,
    "geotrace": AttributeType.TEXT,
    "geoshape": AttributeType.TEXT,
    "barcode": AttributeType.TEXT,
    "intent": AttributeType.TEXT,
}

# Group nodes hold no value; attachments would only yield a filename 121 cannot resolve.
SKIPPED_ODK_TYPES = frozenset({"structure", "binary", "unknown"})

# Repeats arrive as nested arrays, which do not fit 121's flat attribute model.
UNSUPPORTED_ODK_TYPES = frozenset({"repeat"})

# Built-in 121 registration columns: a form may fill them, but they are never created.
BUILT_IN_ATTRIBUTES = frozenset(
    {
        "referenceId",
        "preferredLanguage",
        "paymentAmountMultiplier",
        "maxPayments",
        "programFspConfigurationName",
    }
)

# 121 derives these itself; a form field claiming one of them is a configuration mistake.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "id",
        "programId",
        "status",
        "inclusionScore",
        "registrationProgramId",
        "paymentCount",
        "paymentCountRemaining",
    }
)

# ODK Collect metadata, never meaningful as a 121 registration attribute.
ODK_METADATA_FIELDS = frozenset(
    {
        "instanceid",
        "instancename",
        "deprecatedid",
        "start",
        "end",
        "starttime",
        "endtime",
        "today",
        "deviceid",
        "subscriberid",
        "simserial",
        "username",
        "email",
        "audit",
    }
)

# Only metadata when grouped or prefixed: 121's own 'phoneNumber' differs by case alone.
GROUPED_ONLY_METADATA_FIELDS = frozenset({"phonenumber"})

# Forms either group metadata under 'meta' or flatten it onto the name ('meta_deviceid').
METADATA_GROUP_NAMES = frozenset({"meta", "metadata"})
METADATA_PREFIX_SEPARATORS = ("_", "-")


def _is_odk_metadata(form_field: OdkFormField) -> bool:
    """Metadata is grouped under 'meta', prefixed onto the name, or a known bare name."""
    groups = form_field.path.split("/")[:-1]
    if any(group.lower() in METADATA_GROUP_NAMES for group in groups):
        return True

    name = form_field.name.lower()
    for group in METADATA_GROUP_NAMES:
        for separator in METADATA_PREFIX_SEPARATORS:
            prefix = f"{group}{separator}"
            if name.startswith(prefix):
                return name[len(prefix) :] in ODK_METADATA_FIELDS | GROUPED_ONLY_METADATA_FIELDS

    return name in ODK_METADATA_FIELDS


@dataclass(frozen=True)
class SchemaPlan:
    """What the ODK form implies for 121, derived before the platform is contacted."""

    mappings: tuple[FieldMapping, ...]
    attributes: tuple[ProgramAttribute, ...]


def derive_schema_plan(
    route_id: str,
    schema: OdkFormSchema,
    required_attributes: tuple[str, ...] = (),
) -> tuple[SchemaPlan, list[str]]:
    """Map ODK form fields onto 121 attributes. Pure: no I/O."""
    errors: list[str] = []
    mappings: list[FieldMapping] = []
    attributes: list[ProgramAttribute] = []
    claimed_by: dict[str, str] = {}

    for form_field in schema.fields:
        if form_field.type in UNSUPPORTED_ODK_TYPES:
            errors.append(
                f"{route_id}: field '{form_field.path}' is a {form_field.type}, "
                f"which 121 cannot store"
            )
            continue

        if form_field.type in SKIPPED_ODK_TYPES or _is_odk_metadata(form_field):
            continue

        if form_field.name in FORBIDDEN_ATTRIBUTES:
            errors.append(
                f"{route_id}: field '{form_field.path}' uses '{form_field.name}', "
                f"which 121 generates itself"
            )
            continue

        attribute_type = ODK_TYPE_TO_ATTRIBUTE_TYPE.get(form_field.type)
        if attribute_type is None:
            logger.warning(
                "%s: skipping field '%s' of unmapped type '%s'",
                route_id,
                form_field.path,
                form_field.type,
            )
            continue

        # 121 keys attributes on the leaf name, so two groups cannot share one.
        if form_field.name in claimed_by:
            errors.append(
                f"{route_id}: fields '{claimed_by[form_field.name]}' and '{form_field.path}' "
                f"both map to attribute '{form_field.name}'"
            )
            continue
        claimed_by[form_field.name] = form_field.path

        mappings.append(
            FieldMapping(
                odk_field=form_field.path,
                attribute=form_field.name,
                required=form_field.name in required_attributes,
            )
        )
        if form_field.name not in BUILT_IN_ATTRIBUTES:
            attributes.append(ProgramAttribute(name=form_field.name, type=attribute_type))

    errors.extend(
        f"{route_id}: required attribute '{name}' has no field in ODK form '{schema.form_id}'"
        for name in required_attributes
        if name not in claimed_by
    )
    if not mappings and not errors:
        errors.append(f"{route_id}: ODK form '{schema.form_id}' has no usable fields")

    return SchemaPlan(tuple(mappings), tuple(attributes)), errors


def sync_program_attributes(
    route: RouteConfig,
    client_odk: ClientOdk | None,
    client_121: Client121 | None,
) -> tuple[SchemaPlan | None, list[str]]:
    """Read the ODK form, create whatever 121 is missing, and return the mapping to use."""
    try:
        schema = extract_form_schema(route, client_odk)
    except Exception as exc:  # noqa: BLE001 - report, never crash the run
        return None, [f"{route.route_id}: could not read the ODK form schema: {exc}"]

    plan, errors = derive_schema_plan(route.route_id, schema, route.required_attributes)
    if errors:
        return None, errors

    logger.info(
        "%s: ODK form '%s' maps to %d attributes",
        route.route_id,
        schema.form_id,
        len(plan.mappings),
    )
    if client_121 is None:
        return plan, []

    try:
        existing = client_121.get_registration_attributes(route.program.program_id)
    except (requests.RequestException, ValueError) as exc:
        return None, [f"{route.route_id}: could not list 121 registration attributes: {exc}"]

    _warn_on_type_drift(route.route_id, plan.attributes, existing)

    missing = [attribute for attribute in plan.attributes if attribute.name not in existing]
    if not missing:
        logger.info(
            "%s: program %d already has every attribute",
            route.route_id,
            route.program.program_id,
        )
        return plan, []

    creation_errors = _create_attributes(route, client_121, missing)
    if creation_errors:
        return None, creation_errors
    return plan, []


def _create_attributes(
    route: RouteConfig, client: Client121, attributes: list[ProgramAttribute]
) -> list[str]:
    # 121 has no batch endpoint, so a wide form means one slow request per attribute.
    logger.info(
        "%s: creating %d registration attributes, one request each",
        route.route_id,
        len(attributes),
    )
    progress = with_progress(attributes, f"{route.route_id}: creating attributes", "attr")

    errors: list[str] = []
    for attribute in progress:
        try:
            response = client.create_registration_attribute(
                route.program.program_id, attribute.to_dict()
            )
        except requests.RequestException as exc:
            errors.append(f"{route.route_id}: creating attribute '{attribute.name}' failed: {exc}")
            continue
        if response.status_code not in range(200, 300):
            errors.append(
                f"{route.route_id}: 121 returned {response.status_code} creating "
                f"attribute '{attribute.name}': {response.text[:500]}"
            )
    created = len(attributes) - len(errors)
    if created:
        logger.info("%s: created %d registration attributes", route.route_id, created)
    return errors


def _warn_on_type_drift(
    route_id: str, attributes: tuple[ProgramAttribute, ...], existing: dict[str, str]
) -> None:
    """Existing attributes are never modified, so a changed ODK type only gets logged."""
    for attribute in attributes:
        current = existing.get(attribute.name)
        if current and current != attribute.type.value:
            logger.warning(
                "%s: attribute '%s' is '%s' in 121 but the ODK form now implies '%s'; "
                "leaving it unchanged",
                route_id,
                attribute.name,
                current,
                attribute.type.value,
            )
