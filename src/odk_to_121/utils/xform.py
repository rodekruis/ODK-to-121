"""Parse an ODK XForms definition into questions, labels and choice lists.

Central's `/fields` endpoint reports XForms *binding* types only, so a `select_one`
arrives there indistinguishable from free text and its choices are absent entirely.
Both live in the form definition, which is why this module exists. Pure: no I/O.
"""

from __future__ import annotations

import logging
import re

# Only the Element type comes from the stdlib; parsing goes through defusedxml, because a
# form definition is user-uploaded content and ElementTree expands entities without limit.
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from odk_to_121.data_types.domain_types import (
    OdkChoice,
    OdkFormDefinition,
    OdkQuestion,
    SelectKind,
    Translations,
)

logger = logging.getLogger(__name__)

# Body controls that hold an answer. Groups and repeats are containers, not questions.
SELECT_TAGS: dict[str, SelectKind] = {"select1": SelectKind.ONE, "select": SelectKind.MULTIPLE}
QUESTION_TAGS = frozenset({"input", "upload", "trigger", "range", "rank", *SELECT_TAGS})

# `jr:itext('/data/x:label')` points at a fixed translation; `jr:itext(itextId)` names a
# node to read the id from, which is how itemsets translate each choice separately.
ITEXT_REFERENCE = re.compile(r"""jr:itext\(\s*(?:'([^']*)'|"([^"]*)"|([^)\s]+))\s*\)""")

# Itemsets point at a secondary instance: `instance('district')/root/item[...]`.
INSTANCE_REFERENCE = re.compile(r"""instance\(\s*['"]([^'"]+)['"]\s*\)""")

# XLSForm writes languages as 'English (en)'; 121 keys its labels on the ISO 639-1 code.
LANGUAGE_CODE = re.compile(r"\(([A-Za-z]{2})\)")


def parse_form_definition(xml: bytes) -> OdkFormDefinition:
    """Parse an XForms definition, keyed by the same paths the `/fields` endpoint reports."""
    root: Element = fromstring(xml)
    translations = _read_translations(root)
    choice_lists = _read_choice_lists(root)

    questions: dict[str, OdkQuestion] = {}
    for body in _descendants(root, "body"):
        for control in _descendants(body, *QUESTION_TAGS):
            question = _read_question(control, translations, choice_lists)
            if question is not None:
                questions[question.path] = question
    return OdkFormDefinition(questions=questions)


def _read_question(
    control: Element,
    translations: dict[str, Translations],
    choice_lists: dict[str, list[Element]],
) -> OdkQuestion | None:
    """Build one question from a body control, resolving its label and any choices."""
    path = _to_field_path(control.get("ref"))
    if path is None:
        return None

    select_kind = SELECT_TAGS.get(_local_name(control))
    choices: tuple[OdkChoice, ...] = ()
    if select_kind is not None:
        choices = _read_choices(control, translations, choice_lists)

    return OdkQuestion(
        path=path,
        labels=_read_label(control, translations),
        select_kind=select_kind,
        choices=choices,
    )


def _read_choices(
    control: Element,
    translations: dict[str, Translations],
    choice_lists: dict[str, list[Element]],
) -> tuple[OdkChoice, ...]:
    """Read the options of a select, whether they are inline or in a secondary instance."""
    inline = [
        choice
        for item in _children(control, "item")
        if (choice := _read_inline_choice(item, translations)) is not None
    ]
    if inline:
        return tuple(inline)

    itemset = next(iter(_children(control, "itemset")), None)
    if itemset is None:
        return ()
    return _read_itemset_choices(itemset, translations, choice_lists)


def _read_inline_choice(item: Element, translations: dict[str, Translations]) -> OdkChoice | None:
    """Read `<item><value>code</value><label .../></item>`."""
    value = next(iter(_children(item, "value")), None)
    if value is None or not (value.text or "").strip():
        return None
    return OdkChoice(value=(value.text or "").strip(), labels=_read_label(item, translations))


def _read_itemset_choices(
    itemset: Element,
    translations: dict[str, Translations],
    choice_lists: dict[str, list[Element]],
) -> tuple[OdkChoice, ...]:
    """Resolve `<itemset nodeset="instance('list')/root/item[...]">` against the form's own data.

    Choice lists held in an attached CSV are not part of the definition, so they resolve
    to nothing and the caller falls back to plain text.
    """
    match = INSTANCE_REFERENCE.search(itemset.get("nodeset") or "")
    if match is None:
        return ()
    items = choice_lists.get(match.group(1))
    if not items:
        return ()

    value = next(iter(_children(itemset, "value")), None)
    value_node = value.get("ref") if value is not None else None
    if not value_node:
        return ()

    label = next(iter(_children(itemset, "label")), None)
    label_ref = label.get("ref") if label is not None else None

    choices = []
    for item in items:
        code = _child_text(item, value_node)
        if code is None:
            continue
        choices.append(
            OdkChoice(value=code, labels=_read_itemset_label(item, label_ref, translations))
        )
    return tuple(choices)


def _read_itemset_label(
    item: Element, label_ref: str | None, translations: dict[str, Translations]
) -> Translations:
    """An itemset label names the node each choice keeps its translation id in."""
    match = ITEXT_REFERENCE.search(label_ref or "")
    if match is None:
        return {}

    literal, quoted, node = match.groups()
    text_id = literal or quoted or (_child_text(item, node) if node else None)
    return translations.get(text_id, {}) if text_id else {}


def _read_label(element: Element, translations: dict[str, Translations]) -> Translations:
    """Read a `<label>` child, following `jr:itext(...)` into the translation table.

    A label written straight into the element yields nothing: such forms declare no
    language, and 121 keys every label on an ISO 639-1 code.
    """
    label = next(iter(_children(element, "label")), None)
    if label is None:
        return {}

    match = ITEXT_REFERENCE.search(label.get("ref") or "")
    if match is None:
        return {}
    literal, quoted, _ = match.groups()
    return translations.get(literal or quoted or "", {})


def _read_translations(root: Element) -> dict[str, Translations]:
    """Flatten `<itext>` into `{text id: {language: text}}`."""
    translations: dict[str, Translations] = {}
    for itext in _descendants(root, "itext"):
        for translation in _children(itext, "translation"):
            language = _iso_language_code(translation.get("lang") or "")
            if language is None:
                logger.warning(
                    "ODK form language '%s' carries no ISO 639-1 code; its labels are skipped",
                    translation.get("lang"),
                )
                continue
            for text in _children(translation, "text"):
                value = _translation_text(text)
                if text.get("id") and value:
                    translations.setdefault(text.get("id", ""), {})[language] = value
    return translations


def _translation_text(text: Element) -> str | None:
    """Take the plain value; a `<value form="image">` sibling is media, not a label."""
    for value in _children(text, "value"):
        if value.get("form") is None and (value.text or "").strip():
            return (value.text or "").strip()
    return None


def _read_choice_lists(root: Element) -> dict[str, list[Element]]:
    """Collect the secondary instances that itemsets read their choices from."""
    lists: dict[str, list[Element]] = {}
    for model in _descendants(root, "model"):
        for instance in _children(model, "instance"):
            # An instance with a 'src' lives in an attached file, not in the definition.
            name = instance.get("id")
            if not name or instance.get("src"):
                continue
            for instance_root in instance:
                lists[name] = list(_children(instance_root, "item"))
    return lists


def _to_field_path(ref: str | None) -> str | None:
    """`/data/group/field` -> `group/field`, matching the `/fields` endpoint's paths."""
    if not ref or not ref.startswith("/"):
        return None
    # Drop the leading empty segment and the primary instance root.
    segments = ref.split("/")[2:]
    return "/".join(segments) or None


def _iso_language_code(language: str) -> str | None:
    """'English (en)' -> 'en'. 121 rejects anything that is not an ISO 639-1 code."""
    match = LANGUAGE_CODE.search(language)
    if match is not None:
        return match.group(1).lower()
    return language.lower() if len(language) == 2 and language.isalpha() else None


def _child_text(element: Element, name: str) -> str | None:
    """Text of the first child with the given local name."""
    child = next(iter(_children(element, name)), None)
    return text if child is not None and (text := (child.text or "").strip()) else None


def _children(element: Element, *names: str) -> list[Element]:
    """Direct children matching any local name, ignoring XML namespaces."""
    return [child for child in element if _local_name(child) in names]


def _descendants(element: Element, *names: str) -> list[Element]:
    """Descendants matching any local name, ignoring XML namespaces."""
    return [found for found in element.iter() if _local_name(found) in names]


def _local_name(element: Element) -> str:
    """Tag without its namespace; XForms elements are namespaced, their local names are not."""
    return element.tag.rpartition("}")[2]
