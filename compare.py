"""Compare two RDF files (TriG, Turtle, N-Quads) as sets of canonical N-Quads.

Use it to check a new pipeline against the output of a reference pipeline: parse both sides, write every quad in a canonical N-Quads form, and compare the two sets. Blank nodes are not canonicalised, so the files should not contain any.

Usage: ``python compare.py new.trig reference.trig`` (exit code 1 if they differ).
"""

import sys
from pathlib import Path

import rdflib
from rdflib import XSD, Dataset, Literal
from rdflib.term import Node

FORMATS = {".trig": "trig", ".ttl": "turtle", ".nq": "nquads", ".nt": "nt"}


def canonical(term: Node) -> str:
    """N-Triples form of a term, with two canonicalisations; every other lexical form must match exactly.

    * ``"x"^^xsd:string`` is the plain literal ``"x"`` (they are the same term in RDF 1.1).
    * ``xsd:decimal`` compares by value, because serialisers may write ``2`` as ``2.0``.

    >>> canonical(Literal("x", datatype=XSD.string)) == canonical(Literal("x"))
    True
    >>> canonical(Literal("2", datatype=XSD.decimal)) == canonical(Literal("2.0", datatype=XSD.decimal))
    True
    >>> canonical(Literal("042", datatype=XSD.integer, normalize=False)) == canonical(Literal("42", datatype=XSD.integer))
    False
    """
    if isinstance(term, Literal) and term.datatype == XSD.string:
        return Literal(str(term)).n3()
    if isinstance(term, Literal) and term.datatype == XSD.decimal and term.value is not None:
        return f'"{term.value.normalize()}"^^<{XSD.decimal}>'
    return term.n3()


def canonical_quads(path: Path) -> frozenset[str]:
    """Canonical N-Quads lines of an RDF file. Literals are parsed without normalisation, so lexical forms are compared as written."""
    ds = Dataset()
    saved, rdflib.NORMALIZE_LITERALS = rdflib.NORMALIZE_LITERALS, False
    try:
        ds.parse(path, format=FORMATS.get(path.suffix, "trig"))
    finally:
        rdflib.NORMALIZE_LITERALS = saved
    return frozenset(" ".join(map(canonical, quad)) for quad in ds.quads())


def diff(new: Path, reference: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Quads missing from ``new`` and quads extra in ``new``, compared with ``reference``."""
    a, b = canonical_quads(new), canonical_quads(reference)
    return b - a, a - b


def main(argv: list[str]) -> int:
    missing, extra = diff(Path(argv[1]), Path(argv[2]))
    for line in sorted(missing):
        print("-", line)
    for line in sorted(extra):
        print("+", line)
    print("OK" if not (missing or extra) else f"DIFF -{len(missing)} +{len(extra)}")
    return 1 if missing or extra else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
