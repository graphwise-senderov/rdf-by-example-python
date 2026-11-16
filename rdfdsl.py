"""A small declarative DSL for writing RDF quads from table rows.

A description reads like Turtle:

>>> from rdflib import RDFS
>>> ex = Prefix("https://example.org/")
>>> d = subject(ex.Acme) >> RDFS.label << en("Acme") << de("Acme AG")
>>> len(d.triples)
2

Three rules keep row mappings short:

* ``None`` vanishes. A subject, predicate, object or graph that is ``None`` emits nothing, just like an unbound variable in a SPARQL CONSTRUCT template.
* Lists fan out. A list in any position emits one triple per element.
* An invalid IRI is ``None``. :class:`Prefix` returns ``None`` for an IRI with a forbidden character, as SPARQL ``iri()`` fails on it, so the second rule applies.

``>>`` selects the predicate and ``<<`` adds an object. Both operators have the same precedence and associate to the left, so a chain is read left to right. A plain ``str`` object becomes a plain literal; IRIs are always ``URIRef``.
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import wraps
from itertools import chain, product
from typing import Any, Optional, Union

from rdflib import XSD, BNode, Dataset, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID

Term = Union[URIRef, Literal, BNode]
Quad = tuple[Term, Term, Term, URIRef]

DEFAULT_GRAPH = DATASET_DEFAULT_GRAPH_ID
"""Graph name for triples that belong in the default graph."""


def fan(value: Any) -> tuple[Term, ...]:
    """Normalise a value to a tuple of RDF terms.

    >>> fan(None), fan("x"), fan([URIRef("urn:a"), None, ["y"]])
    ((), (rdflib.term.Literal('x'),), (rdflib.term.URIRef('urn:a'), rdflib.term.Literal('y')))
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(chain.from_iterable(map(fan, value)))
    if isinstance(value, (URIRef, Literal, BNode)):
        return (value,)
    if isinstance(value, str):
        return (Literal(value),)
    raise TypeError(f"not an RDF value: {value!r}")


@dataclass(frozen=True)
class Subject:
    """Immutable builder: the subjects, the current predicates and the triples so far."""

    nodes: tuple[Term, ...]
    predicates: tuple[Term, ...] = ()
    triples: tuple[tuple[Term, Term, Term], ...] = ()

    def __rshift__(self, predicate: Any) -> "Subject":
        return replace(self, predicates=fan(predicate))

    def __lshift__(self, obj: Any) -> "Subject":
        added = tuple(product(self.nodes, self.predicates, fan(obj)))
        return replace(self, triples=self.triples + added)


def subject(node: Any) -> Subject:
    """Start a description of ``node`` (a term, a list of terms, or ``None``).

    >>> s = subject(None) >> URIRef("urn:p") << "o"
    >>> s.triples
    ()
    >>> s = subject([URIRef("urn:a"), URIRef("urn:b")]) >> URIRef("urn:p") << ["x", "y"]
    >>> len(s.triples)
    4
    """
    return Subject(fan(node))


def graph(name: Any, *descriptions: Subject) -> tuple[Quad, ...]:
    """Place descriptions into the named graph(s) ``name``.

    >>> d = subject(URIRef("urn:s")) >> URIRef("urn:p") << "o"
    >>> len(graph([URIRef("urn:g1"), URIRef("urn:g2")], d)), graph(None, d)
    (2, ())
    """
    return tuple((s, p, o, g) for g in fan(name) for d in descriptions for s, p, o in d.triples)


def quads(*blocks: Iterable[Quad]) -> tuple[Quad, ...]:
    """Concatenate blocks of quads.

    >>> d = subject(URIRef("urn:s")) >> URIRef("urn:p") << "o"
    >>> len(quads(graph(URIRef("urn:g1"), d), graph(URIRef("urn:g2"), d)))
    2
    """
    return tuple(chain.from_iterable(blocks))


NOT_IN_IRI = frozenset(' <>"{}|\\^`') | frozenset(map(chr, range(0x21)))


def valid_iri(text: str) -> Optional[URIRef]:
    """The IRI, or ``None`` if it contains a character that IRIs forbid.

    >>> valid_iri("https://example.org/a"), valid_iri("https://example.org/a b")
    (rdflib.term.URIRef('https://example.org/a'), None)
    """
    return None if NOT_IN_IRI.intersection(text) else URIRef(text)


@dataclass(frozen=True)
class Prefix:
    """IRI prefix with ``None``-aware lookup.

    ``P["a", "b"]`` joins the parts with ``/``. A ``None`` part gives ``None``, a list part fans out into a list of IRIs, and an invalid IRI gives ``None``. Attribute access names a fixed term.

    >>> ex = Prefix("https://example.org/")
    >>> ex["org", "acme"], ex.Organisation
    (rdflib.term.URIRef('https://example.org/org/acme'), rdflib.term.URIRef('https://example.org/Organisation'))
    >>> ex["org", None] is None, ex["org", "a b"] is None
    (True, True)
    >>> ex["sector", ["Energy", "Water"]]
    [rdflib.term.URIRef('https://example.org/sector/Energy'), rdflib.term.URIRef('https://example.org/sector/Water')]
    """

    base: str

    def __getitem__(self, key: Any) -> Any:
        parts = key if isinstance(key, tuple) else (key,)
        if any(isinstance(p, list) for p in parts):
            options = [p if isinstance(p, list) else [p] for p in parts]
            return [self[combo] for combo in product(*options)]
        if any(p is None for p in parts):
            return None
        return valid_iri(self.base + "/".join(map(str, parts)))

    def __getattr__(self, name: str) -> URIRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return URIRef(self.base + name)


def cell(f: Callable[..., Any]) -> Callable[..., Any]:
    """Lift a function on ``str`` to cell values: ``None`` stays ``None``, lists map element by element.

    >>> shout = cell(str.upper)
    >>> shout("a"), shout(None), shout(["a", "b"])
    ('A', None, ['A', 'B'])
    """

    @wraps(f)
    def lifted(value: Any, *args: Any, **kwargs: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, list):
            return [lifted(v, *args, **kwargs) for v in value]
        return f(value, *args, **kwargs)

    return lifted


iri = cell(valid_iri)
"""IRI maker for a cell that holds a full IRI: ``None`` and invalid IRIs give ``None``."""

lit = cell(Literal)
"""Plain literal maker: ``lit("x")`` is ``"x"``."""


def lang(tag: str) -> Callable[[Any], Any]:
    """Literal maker for a language tag.

    >>> de("Wasser"), de(None)
    (rdflib.term.Literal('Wasser', lang='de'), None)
    """
    return cell(lambda text: Literal(text, lang=tag))


def typed(datatype: URIRef) -> Callable[[Any], Any]:
    """Literal maker for a datatype; the lexical form is kept as it is.

    >>> integer("042")
    rdflib.term.Literal('042', datatype=rdflib.term.URIRef('http://www.w3.org/2001/XMLSchema#integer'))
    """
    return cell(lambda text: Literal(text, datatype=datatype, normalize=False))


de, en, fr, it = map(lang, ("de", "en", "fr", "it"))
integer = typed(XSD.integer)
decimal = typed(XSD.decimal)
boolean = typed(XSD.boolean)
date = typed(XSD.date)


class Row(Mapping):
    """One table row. Attribute access gives the cell, or ``None`` if it is empty or absent.

    >>> r = Row({"id": "acme", "homepage": ""})
    >>> r.id, r.homepage, r.missing
    ('acme', None, None)
    """

    __slots__ = ("_cells",)

    def __init__(self, cells: Mapping) -> None:
        self._cells = {k: v.strip() for k, v in cells.items() if v is not None and v.strip() != ""}

    def __getattr__(self, column: str) -> Optional[str]:
        if column.startswith("_"):
            raise AttributeError(column)
        return self._cells.get(column)

    def __getitem__(self, column: str) -> str:
        return self._cells[column]

    def __iter__(self) -> Iterator[str]:
        return iter(self._cells)

    def __len__(self) -> int:
        return len(self._cells)


def dataset(all_quads: Iterable[Quad], prefixes: Mapping[str, str] = {}) -> Dataset:
    """Collect quads into an rdflib ``Dataset`` with the given prefixes bound.

    >>> d = subject(URIRef("urn:s")) >> URIRef("urn:p") << "o"
    >>> sum(1 for _ in dataset(graph(URIRef("urn:g"), d)).quads())
    1
    """
    ds = Dataset()
    for prefix, namespace in prefixes.items():
        ds.bind(prefix, namespace)
    ds.addN((s, p, o, ds.graph(g)) for s, p, o, g in all_quads)
    return ds
