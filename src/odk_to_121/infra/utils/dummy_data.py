"""Dummy form and submissions for the `debug` run target. TODO: use a real ODK test form."""

from __future__ import annotations

from typing import Any

# Shaped like ODK Central's `/fields?odata=true` response.
DUMMY_FORM_FIELDS: list[dict[str, Any]] = [
    {"path": "/person", "name": "person", "type": "structure"},
    {"path": "/person/fullName", "name": "fullName", "type": "string"},
    {"path": "/person/phoneNumber", "name": "phoneNumber", "type": "string"},
    {"path": "/household", "name": "household", "type": "structure"},
    {"path": "/household/householdSize", "name": "householdSize", "type": "int"},
    {"path": "/meta", "name": "meta", "type": "structure"},
    {"path": "/meta/instanceID", "name": "instanceID", "type": "string"},
]

DUMMY_SUBMISSION_ROWS: list[dict[str, Any]] = [
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000001",
        "__system": {"submissionDate": "2026-01-15T09:30:00.000Z", "reviewState": "approved"},
        "person": {"fullName": "Ada Lovelace", "phoneNumber": "31600000001"},
        "household": {"householdSize": 4},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000002",
        "__system": {"submissionDate": "2026-01-15T10:05:00.000Z", "reviewState": None},
        "person": {"fullName": "Grace Hopper", "phoneNumber": "31600000002"},
        "household": {"householdSize": 2},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000003",
        "__system": {"submissionDate": "2026-01-15T11:00:00.000Z", "reviewState": "rejected"},
        "person": {"fullName": "Rejected Record", "phoneNumber": "31600000003"},
        "household": {"householdSize": 1},
    },
]
