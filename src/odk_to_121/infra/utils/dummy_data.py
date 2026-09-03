"""Dummy submissions for the `debug` run target. TODO: replace with a real ODK test form."""

from __future__ import annotations

from typing import Any

DUMMY_SUBMISSION_ROWS: list[dict[str, Any]] = [
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000001",
        "__system": {"submissionDate": "2026-01-15T09:30:00.000Z", "reviewState": "approved"},
        "person": {"full_name": "Ada Lovelace", "phone_number": "31600000001"},
        "household": {"size": 4},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000002",
        "__system": {"submissionDate": "2026-01-15T10:05:00.000Z", "reviewState": None},
        "person": {"full_name": "Grace Hopper", "phone_number": "31600000002"},
        "household": {"size": 2},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000003",
        "__system": {"submissionDate": "2026-01-15T11:00:00.000Z", "reviewState": "rejected"},
        "person": {"full_name": "Rejected Record", "phone_number": "31600000003"},
        "household": {"size": 1},
    },
]
