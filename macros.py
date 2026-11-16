"""Python functions that replace typical C preprocessor macros of RDF by Example templates.

Every function accepts a cell value: ``None`` (an empty cell) passes through, and a list (a split cell) is mapped element by element, so the functions compose like the macros did.
"""

import re
from collections.abc import Mapping
from typing import Any, Optional

from rdflib import URIRef
from rdflib.namespace import RDF, RDFS, XSD

from rdfdsl import Split, cell, split, valid_iri

TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
EMPTY_MARKERS = frozenset({"", "-", "n/a", "N/A", "none", "None"})

PREFIXES: dict[str, str] = {
    "rdf": str(RDF),
    "rdfs": str(RDFS),
    "xsd": str(XSD),
    "schema": "https://schema.org/",
    "ex": "https://example.org/",
}
"""Prefixes known to :func:`curie`."""


@cell
def transliterate(text: str) -> str:
    """Spell out German umlauts and ß.

    >>> transliterate("Grün & Söhne")
    'Gruen & Soehne'
    """
    return text.translate(TRANSLITERATION)


@cell
def urlify(text: str) -> str:
    """Transliterate, then keep only letters and digits (macro URLIFY).

    >>> urlify("Grün & Söhne GmbH"), urlify(["Public Sector", "R&D"]), urlify(None)
    ('GruenSoehneGmbH', ['PublicSector', 'RD'], None)
    """
    return "".join(c for c in transliterate(text) if c.isalnum())


def _split(text: Optional[str], pattern: str) -> Optional[Split]:
    if text is None:
        return None
    return split(part.strip() for part in re.split(pattern, text) if part.strip())


def split_comma(text: Optional[str]) -> Optional[list[str]]:
    """Split a multi-valued cell on commas (macro SPLIT).

    >>> split_comma("Energy, Water,Transport"), split_comma(None)
    (['Energy', 'Water', 'Transport'], None)
    """
    return _split(text, ",")


def split_semi(text: Optional[str]) -> Optional[list[str]]:
    """Split a multi-valued cell on semicolons (macro SPLIT_SEMI).

    >>> split_semi("CEO; founder")
    ['CEO', 'founder']
    """
    return _split(text, ";")


@cell
def if_not_empty(text: str) -> Optional[str]:
    """``None`` for placeholders that mean "no value" (macro IFNOT_EMPTY).

    >>> if_not_empty("n/a") is None, if_not_empty("DE")
    (True, 'DE')
    """
    return None if text in EMPTY_MARKERS else text


@cell
def curie(text: str, prefixes: Mapping[str, str] = PREFIXES) -> Optional[URIRef]:
    """Expand a prefixed name such as ``schema:NGO`` to an IRI (macro CURIE); unknown prefixes give ``None``.

    >>> curie("schema:NGO"), curie("nope:x"), curie(None)
    (rdflib.term.URIRef('https://schema.org/NGO'), None, None)
    """
    prefix, colon, local = text.partition(":")
    if not colon or prefix not in prefixes:
        return None
    return valid_iri(prefixes[prefix] + local)


def dash_if(text: Any) -> Any:
    """``-text`` if there is a value, else the empty string (macro DASH_IF); for optional name parts.

    >>> "Jane" + dash_if("Doe"), "Jane" + dash_if(None), dash_if(["a", None])
    ('Jane-Doe', 'Jane', ['-a', ''])
    """
    if isinstance(text, Split):
        return text.derive(dash_if(t) for t in text)
    if isinstance(text, list):
        return [dash_if(t) for t in text]
    return "" if text is None else "-" + text
