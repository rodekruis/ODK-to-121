from __future__ import annotations

import logging

import pytest

from odk_to_121.data_types.domain_types import SelectKind
from odk_to_121.utils.xform import parse_form_definition


def _form(model: str = "", body: str = "") -> bytes:
    """Wrap model and body fragments in the XForms envelope Central serves."""
    return f"""<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml"
        xmlns:jr="http://openrosa.org/javarosa">
  <h:head><model>{model}</model></h:head>
  <h:body>{body}</h:body>
</h:html>
""".encode()


ENGLISH_AND_ARABIC = """
<itext>
  <translation default="true()" lang="English (en)">
    <text id="/data/gender:label"><value>Gender</value></text>
    <text id="/data/gender/female:label"><value>Female</value></text>
  </translation>
  <translation lang="Arabic (ar)">
    <text id="/data/gender:label"><value>الجنس</value></text>
    <text id="/data/gender/female:label"><value>أنثى</value></text>
  </translation>
</itext>
"""


def test_a_select_one_with_inline_items_yields_its_choices_in_every_language() -> None:
    definition = parse_form_definition(
        _form(
            model=ENGLISH_AND_ARABIC,
            body="""
            <select1 ref="/data/gender">
              <label ref="jr:itext('/data/gender:label')"/>
              <item>
                <label ref="jr:itext('/data/gender/female:label')"/>
                <value>female</value>
              </item>
            </select1>
            """,
        )
    )

    question = definition.get("gender")
    assert question is not None
    assert question.select_kind is SelectKind.ONE
    assert question.labels == {"en": "Gender", "ar": "الجنس"}
    assert [(c.value, c.labels) for c in question.choices] == [
        ("female", {"en": "Female", "ar": "أنثى"})
    ]


def test_group_paths_match_the_fields_endpoint() -> None:
    definition = parse_form_definition(
        _form(body='<group ref="/data/person"><input ref="/data/person/details/fullName"/></group>')
    )

    # The primary instance root is dropped, exactly as Central drops it from '/fields'.
    assert set(definition.questions) == {"person/details/fullName"}


def test_a_select_multiple_is_recognised_but_kept_apart() -> None:
    definition = parse_form_definition(
        _form(body='<select ref="/data/needs"><item><value>food</value></item></select>')
    )

    question = definition.get("needs")
    assert question is not None
    assert question.select_kind is SelectKind.MULTIPLE


def test_choices_held_in_a_secondary_instance_are_resolved() -> None:
    definition = parse_form_definition(
        _form(
            model="""
            <itext>
              <translation lang="English (en)">
                <text id="district-0"><value>Aleppo City</value></text>
              </translation>
            </itext>
            <instance id="district">
              <root>
                <item><itextId>district-0</itextId><name>aleppo_city</name></item>
              </root>
            </instance>
            """,
            body="""
            <select1 ref="/data/district">
              <itemset nodeset="instance('district')/root/item[governorate= /data/governorate ]">
                <value ref="name"/>
                <label ref="jr:itext(itextId)"/>
              </itemset>
            </select1>
            """,
        )
    )

    question = definition.get("district")
    assert question is not None
    # The filter is ignored on purpose: 121 must accept every value ODK can produce.
    assert [(c.value, c.labels) for c in question.choices] == [
        ("aleppo_city", {"en": "Aleppo City"})
    ]


def test_choices_kept_in_an_attached_file_resolve_to_nothing() -> None:
    definition = parse_form_definition(
        _form(
            model='<instance id="district" src="jr://file-csv/district.csv"><root/></instance>',
            body="""
            <select1 ref="/data/district">
              <itemset nodeset="instance('district')/root/item">
                <value ref="name"/>
              </itemset>
            </select1>
            """,
        )
    )

    question = definition.get("district")
    assert question is not None
    assert question.select_kind is SelectKind.ONE
    assert question.choices == ()


def test_an_itemset_naming_an_unknown_list_resolves_to_nothing() -> None:
    definition = parse_form_definition(
        _form(
            body="""
            <select1 ref="/data/district">
              <itemset nodeset="instance('missing')/root/item">
                <value ref="name"/>
              </itemset>
            </select1>
            """,
        )
    )

    question = definition.get("district")
    assert question is not None
    assert question.choices == ()


def test_an_item_without_a_value_is_not_an_option() -> None:
    """An empty option would be sent to 121 as a value it then accepts from anyone."""
    definition = parse_form_definition(
        _form(
            body="""
            <select1 ref="/data/gender">
              <item><value>female</value></item>
              <item><value>  </value></item>
              <item/>
            </select1>
            """
        )
    )

    question = definition.get("gender")
    assert question is not None
    assert [c.value for c in question.choices] == ["female"]


def test_a_control_without_an_absolute_ref_is_ignored() -> None:
    definition = parse_form_definition(_form(body='<input ref="relative"/><input/>'))

    assert definition.questions == {}


LABELLED_INPUT = """<input ref="/data/name"><label ref="jr:itext('/data/name:label')"/></input>"""


def test_a_language_without_an_iso_code_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        definition = parse_form_definition(
            _form(
                model="""
                <itext>
                  <translation lang="default">
                    <text id="/data/name:label"><value>Name</value></text>
                  </translation>
                </itext>
                """,
                body=LABELLED_INPUT,
            )
        )

    question = definition.get("name")
    assert question is not None
    assert question.labels == {}
    assert "carries no ISO 639-1 code" in caplog.text


def test_a_label_written_into_the_form_carries_no_language_so_it_is_dropped() -> None:
    definition = parse_form_definition(
        _form(body='<input ref="/data/name"><label>Name</label></input>')
    )

    question = definition.get("name")
    assert question is not None
    assert question.labels == {}


def test_media_values_are_not_mistaken_for_labels() -> None:
    definition = parse_form_definition(
        _form(
            model="""
            <itext>
              <translation lang="English (en)">
                <text id="/data/name:label">
                  <value form="image">jr://images/name.png</value>
                  <value>Name</value>
                </text>
              </translation>
            </itext>
            """,
            body=LABELLED_INPUT,
        )
    )

    question = definition.get("name")
    assert question is not None
    assert question.labels == {"en": "Name"}
