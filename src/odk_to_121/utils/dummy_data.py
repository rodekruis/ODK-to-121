"""Dummy form and submissions for the `debug` environment. TODO: use a real ODK test form."""

from __future__ import annotations

from typing import Any

# Shaped like ODK Central's `/fields?odata=true` response.
DUMMY_FORM_FIELDS: list[dict[str, Any]] = [
    {"path": "/person", "name": "person", "type": "structure"},
    {"path": "/person/fullName", "name": "fullName", "type": "string"},
    {"path": "/person/phoneNumber", "name": "phoneNumber", "type": "string"},
    {"path": "/person/gender", "name": "gender", "type": "string"},
    {"path": "/household", "name": "household", "type": "structure"},
    {"path": "/household/householdSize", "name": "householdSize", "type": "int"},
    {"path": "/meta", "name": "meta", "type": "structure"},
    {"path": "/meta/instanceID", "name": "instanceID", "type": "string"},
]

# Shaped like ODK Central's `GET /v1/projects/{p}/forms/{f}.xml` response. 'gender' is a
# select_one so the debug run exercises the dropdown path; the rest stay plain text.
DUMMY_FORM_DEFINITION = b"""<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml"
        xmlns:jr="http://openrosa.org/javarosa">
  <h:head>
    <model>
      <itext>
        <translation default="true()" lang="English (en)">
          <text id="/data/person/fullName:label"><value>Full name</value></text>
          <text id="/data/person/phoneNumber:label"><value>Phone number</value></text>
          <text id="/data/person/gender:label"><value>Gender</value></text>
          <text id="/data/person/gender/female:label"><value>Female</value></text>
          <text id="/data/person/gender/male:label"><value>Male</value></text>
          <text id="/data/household/householdSize:label"><value>Household size</value></text>
        </translation>
      </itext>
    </model>
  </h:head>
  <h:body>
    <group ref="/data/person">
      <input ref="/data/person/fullName">
        <label ref="jr:itext('/data/person/fullName:label')"/>
      </input>
      <input ref="/data/person/phoneNumber">
        <label ref="jr:itext('/data/person/phoneNumber:label')"/>
      </input>
      <select1 ref="/data/person/gender">
        <label ref="jr:itext('/data/person/gender:label')"/>
        <item>
          <label ref="jr:itext('/data/person/gender/female:label')"/>
          <value>female</value>
        </item>
        <item>
          <label ref="jr:itext('/data/person/gender/male:label')"/>
          <value>male</value>
        </item>
      </select1>
    </group>
    <group ref="/data/household">
      <input ref="/data/household/householdSize">
        <label ref="jr:itext('/data/household/householdSize:label')"/>
      </input>
    </group>
  </h:body>
</h:html>
"""

DUMMY_SUBMISSION_ROWS: list[dict[str, Any]] = [
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000001",
        "__system": {"submissionDate": "2026-01-15T09:30:00.000Z", "reviewState": "approved"},
        "person": {
            "fullName": "Ada Lovelace",
            "phoneNumber": "31600000001",
            "gender": "female",
        },
        "household": {"householdSize": 4},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000002",
        "__system": {"submissionDate": "2026-01-15T10:05:00.000Z", "reviewState": None},
        "person": {
            "fullName": "Grace Hopper",
            "phoneNumber": "31600000002",
            "gender": "female",
        },
        "household": {"householdSize": 2},
    },
    {
        "__id": "uuid:00000000-0000-0000-0000-000000000003",
        "__system": {"submissionDate": "2026-01-15T11:00:00.000Z", "reviewState": "rejected"},
        "person": {
            "fullName": "Rejected Record",
            "phoneNumber": "31600000003",
            "gender": "male",
        },
        "household": {"householdSize": 1},
    },
]
