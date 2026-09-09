"""Decide which 121 FSP configuration a route's registrations are created under.

121 rejects a registration that names no FSP configuration, so every route needs one.
It is resolved per run rather than configured, because 121 already knows the answer:

1. an ODK question named `programFspConfigurationName` chooses one per registration;
2. otherwise a program with exactly one configuration implies it;
3. a program with none, or with several and no question to pick between them, is a setup
   mistake that aborts the route.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from odk_to_121.data_types.config_types import RouteConfig
from odk_to_121.data_types.domain_types import FieldMapping
from odk_to_121.data_types.output_types import FSP_CONFIGURATION_ATTRIBUTE
from odk_to_121.utils.client_121 import Client121

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FspConfigurationPlan:
    """How one route's registrations get their 121 FSP configuration."""

    # Stamped on every registration; None when the ODK form names one per registration.
    default_name: str | None = None
    # Every name the 121 program accepts; empty when 121 was not contacted.
    known_names: frozenset[str] = frozenset()


def resolve_fsp_configuration(
    route: RouteConfig,
    mappings: tuple[FieldMapping, ...],
    client_121: Client121 | None,
) -> tuple[FspConfigurationPlan | None, list[str]]:
    """Pick the route's FSP configuration, or explain why the route cannot run."""
    chosen_by_form = any(mapping.attribute == FSP_CONFIGURATION_ATTRIBUTE for mapping in mappings)

    # Local output and dry runs never reach 121, so there is nothing to reconcile with.
    if client_121 is None:
        return FspConfigurationPlan(), []

    program_id = route.program.program_id
    try:
        known_names = client_121.get_fsp_configuration_names(program_id)
    except (requests.RequestException, ValueError) as exc:
        if chosen_by_form:
            logger.warning(
                "%s: could not list the FSP configurations of 121 program %d, so the "
                "names the ODK form supplies go unchecked: %s",
                route.route_id,
                program_id,
                exc,
            )
            return FspConfigurationPlan(), []
        return None, [
            f"{route.route_id}: could not list the FSP configurations of "
            f"121 program {program_id}: {exc}"
        ]

    if chosen_by_form:
        logger.info(
            "%s: ODK form '%s' picks the FSP configuration per registration",
            route.route_id,
            route.odk.form_id,
        )
        return FspConfigurationPlan(known_names=known_names), []

    if not known_names:
        return None, [
            f"{route.route_id}: 121 program {program_id} has no FSP configurations, "
            f"so it cannot accept registrations; add one in the 121 portal"
        ]

    if len(known_names) > 1:
        return None, [
            f"{route.route_id}: 121 program {program_id} has {len(known_names)} FSP "
            f"configurations ({', '.join(sorted(known_names))}), so the pipeline cannot "
            f"pick one; add a '{FSP_CONFIGURATION_ATTRIBUTE}' question to ODK form "
            f"'{route.odk.form_id}' to choose per registration"
        ]

    (only_name,) = known_names
    logger.info(
        "%s: 121 program %d has one FSP configuration, using '%s'",
        route.route_id,
        program_id,
        only_name,
    )
    return FspConfigurationPlan(default_name=only_name, known_names=known_names), []
