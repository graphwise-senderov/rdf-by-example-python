"""A small declarative DSL for writing RDF quads from table rows.

A description reads like Turtle:

>>> from rdflib import RDFS
>>> ex = Prefix("https://example.org/")
>>> d = subject(ex.Acme) >> RDFS.label << en("Acme") << de("Acme AG")
>>> len(d.triples)
2

Three rules keep row mappings short:

* ``None`` vanishes. A subject, predicate, object or graph that is ``None`` emits nothing, just like an unbound variable in a SPARQL CONSTRUCT template.
* Lists fan out. A list in any position emits one triple per element. Values derived from the same split cell stay paired: element *i* is only combined with element *i* of that split, while values from different splits combine in every way, as separate SPARQL splits do.
* An invalid IRI is ``None``. :class:`Prefix` returns ``None`` for an IRI with a forbidden character, as SPARQL ``iri()`` fails on it, so the second rule applies.

``>>`` selects the predicate and ``<<`` adds an object. Both operators have the same precedence and associate to the left, so a chain is read left to right. A plain ``str`` object becomes a plain literal; IRIs are always ``URIRef``.
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import wraps
from itertools import chain, count, product
from typing import Any, Optional, Union

from rdflib import XSD, BNode, Dataset, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID

Term = Union[URIRef, Literal, BNode]
Quad = tuple[Term, Term, Term, URIRef]

DEFAULT_GRAPH = DATASET_DEFAULT_GRAPH_ID
"""Graph name for triples that belong in the default graph."""


Binding = tuple[tuple[int, int], ...]
"""Which element of which split a term came from: sorted ``(split key, index)`` pairs."""

_keys = count()


class Split(list):
    """A list that came from one split cell.

    Every value derived from it element by element (through :func:`cell` functions and :class:`Prefix`) keeps the same ``key``, so that :class:`Subject` can pair element *i* with element *i*.

    >>> a = Split(["x", "y"])
    >>> b = a.derive(v.upper() for v in a)
    >>> b, b.key == a.key
    (['X', 'Y'], True)
    """

    def __init__(self, values: Iterable[Any] = (), key: Optional[int] = None) -> None:
        super().__init__(values)
        self.key = next(_keys) if key is None else key

    def derive(self, values: Iterable[Any]) -> "Split":
        """A new list with the same key, for values computed element by element."""
        return Split(values, self.key)


def split(values: Optional[Iterable[Any]]) -> Optional[Split]:
    """Mark a list as the elements of one split cell; ``None`` stays ``None``."""
    return None if values is None else Split(values)


def merge(a: Binding, b: Binding) -> Optional[Binding]:
    """Combine two bindings, or ``None`` if they pick different elements of the same split.

    >>> merge(((1, 0),), ((2, 1),)), merge(((1, 0),), ((1, 0),)), merge(((1, 0),), ((1, 1),))
    (((1, 0), (2, 1)), ((1, 0),), None)
    """
    out = dict(a)
    for key, index in b:
        if out.setdefault(key, index) != index:
            return None
    return tuple(sorted(out.items()))


def bound(value: Any, binding: Binding = ()) -> tuple[tuple[Term, Binding], ...]:
    """Normalise a value to RDF terms, each with the split elements it depends on."""
    if value is None:
        return ()
    if isinstance(value, Split):
        out: list[tuple[Term, Binding]] = []
        for i, v in enumerate(value):
            b = merge(binding, ((value.key, i),))
            if b is not None:
                out.extend(bound(v, b))
        return tuple(out)
    if isinstance(value, (list, tuple)):
        return tuple(chain.from_iterable(bound(v, binding) for v in value))
    if isinstance(value, (URIRef, Literal, BNode)):
        return ((value, binding),)
    if isinstance(value, str):
        return ((Literal(value), binding),)
    raise TypeError(f"not an RDF value: {value!r}")


def fan(value: Any) -> tuple[Term, ...]:
    """Normalise a value to a tuple of RDF terms.

    >>> fan(None), fan("x"), fan([URIRef("urn:a"), None, ["y"]])
    ((), (rdflib.term.Literal('x'),), (rdflib.term.URIRef('urn:a'), rdflib.term.Literal('y')))
    """
    return tuple(term for term, _ in bound(value))


def combine(*positions: tuple[tuple[Term, Binding], ...]) -> Iterator[tuple[tuple[Term, ...], Binding]]:
    """Every combination of terms whose bindings agree, with the merged binding."""
    for combo in product(*positions):
        binding: Optional[Binding] = ()
        for _, b in combo:
            binding = merge(binding, b)
            if binding is None:
                break
        if binding is not None:
            yield tuple(t for t, _ in combo), binding


@dataclass(frozen=True)
class Subject:
    """Immutable builder: the subjects, the current predicates and the triples so far, each with its split binding."""

    nodes: tuple[tuple[Term, Binding], ...]
    predicates: tuple[tuple[Term, Binding], ...] = ()
    bound_triples: tuple[tuple[tuple[Term, Term, Term], Binding], ...] = ()

    def __rshift__(self, predicate: Any) -> "Subject":
        return replace(self, predicates=bound(predicate))

    def __lshift__(self, obj: Any) -> "Subject":
        added = tuple(combine(self.nodes, self.predicates, bound(obj)))
        return replace(self, bound_triples=self.bound_triples + added)

    @property
    def triples(self) -> tuple[tuple[Term, Term, Term], ...]:
        """The triples, without their bindings."""
        return tuple(t for t, _ in self.bound_triples)


def subject(node: Any) -> Subject:
    """Start a description of ``node`` (a term, a list of terms, or ``None``).

    >>> s = subject(None) >> URIRef("urn:p") << "o"
    >>> s.triples
    ()
    >>> s = subject([URIRef("urn:a"), URIRef("urn:b")]) >> URIRef("urn:p") << ["x", "y"]
    >>> len(s.triples)
    4

    Values derived from the same split stay paired; different splits combine in every way:

    >>> ex = Prefix("urn:x:")
    >>> names = split(["Energy", "Water"])
    >>> len((subject(ex["sector", names]) >> ex.name << names).triples)
    2
    >>> len((subject(ex["sector", names]) >> ex.name << split(["a", "b"])).triples)
    4
    """
    return Subject(bound(node))


def graph(name: Any, *descriptions: Subject) -> tuple[Quad, ...]:
    """Place descriptions into the named graph(s) ``name``.

    >>> d = subject(URIRef("urn:s")) >> URIRef("urn:p") << "o"
    >>> len(graph([URIRef("urn:g1"), URIRef("urn:g2")], d)), graph(None, d)
    (2, ())
    """
    names = bound(name)
    return tuple((s, p, o, g) for d in descriptions
                 for ((s, p, o), (g,)), _ in combine(d.bound_triples, names_as_tuples(names)))


def names_as_tuples(names: tuple[tuple[Term, Binding], ...]) -> tuple[tuple[tuple[Term], Binding], ...]:
    """Wrap each graph name in a 1-tuple, so it combines like a triple."""
    return tuple(((g,), b) for g, b in names)


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
        lists = [p for p in parts if isinstance(p, list)]
        if len(lists) == 1 and isinstance(lists[0], Split):
            values = lists[0]
            return values.derive(self[tuple(v if p is values else p for p in parts)] for v in values)
        if lists:
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
        if isinstance(value, Split):
            return value.derive(lifted(v, *args, **kwargs) for v in value)
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
