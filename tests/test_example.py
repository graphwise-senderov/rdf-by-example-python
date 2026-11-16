"""Build the example and check specific quads."""

from pathlib import Path

import pytest
from rdflib import RDF, Dataset, Literal, URIRef, XSD

import compare
from example.build import build
from example.mapping import EX, ORGANISATIONS, PEOPLE, SCHEMA

ACME = EX["org", "acme"]
GRUEN = EX["org", "gruen"]
LUMEN = EX["org", "lumen"]
OPEN_GRID = EX["org", "open-grid"]


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return build()


def objects(ds: Dataset, s, p, g=None) -> set:
    return {o for s_, p_, o, g_ in ds.quads((s, p, None, g))}


def test_named_graphs_are_used(ds: Dataset) -> None:
    graphs = {g for _, _, _, g in ds.quads()}
    assert graphs == {ORGANISATIONS, PEOPLE}
    assert (ACME, RDF.type, SCHEMA.Corporation, ORGANISATIONS) in set(ds.quads())
    assert objects(ds, ACME, RDF.type, PEOPLE) == set()


def test_empty_cell_emits_nothing(ds: Dataset) -> None:
    assert objects(ds, GRUEN, SCHEMA.url) == set()                  # empty homepage
    assert objects(ds, LUMEN, SCHEMA.numberOfEmployees) == set()    # empty employees
    assert objects(ds, LUMEN, RDF.type) == set()                    # empty type
    assert objects(ds, EX["person", "p2"], SCHEMA.email) == set()   # empty email
    assert objects(ds, EX["person", "p5"], SCHEMA.familyName) == set()


def test_placeholder_and_invalid_iri_emit_nothing(ds: Dataset) -> None:
    assert objects(ds, OPEN_GRID, SCHEMA.addressCountry) == set()   # "n/a" through if_not_empty
    assert objects(ds, OPEN_GRID, SCHEMA.url) == set()              # homepage with a space


def test_list_fans_out(ds: Dataset) -> None:
    assert objects(ds, OPEN_GRID, EX.sector) == {EX["sector", s] for s in ("Energy", "Research", "OpenData")}
    assert objects(ds, EX["person", "p1"], SCHEMA.roleName) == {Literal("CEO", lang="en"), Literal("Board Member", lang="en")}
    assert objects(ds, EX["sector", "OpenData"], SCHEMA.name) == {Literal("Open Data", lang="en")}


def test_values_and_non_ascii(ds: Dataset) -> None:
    assert objects(ds, GRUEN, SCHEMA.name) == {Literal("Grün & Söhne GmbH")}
    assert objects(ds, GRUEN, SCHEMA.alternateName) == {Literal("GruenSoehneGmbH")}
    assert objects(ds, EX["person", "p2"], EX.handle) == {Literal("Juergen-Mueller")}
    assert objects(ds, EX["person", "p4"], EX.handle) == {Literal("Łukasz-Nowak")}
    assert objects(ds, EX["person", "p5"], EX.handle) == {Literal("Sofia")}
    assert objects(ds, ACME, SCHEMA.numberOfEmployees) == {Literal("1200", datatype=XSD.integer)}


def test_written_file_round_trips(ds: Dataset, tmp_path: Path) -> None:
    a, b = tmp_path / "a.trig", tmp_path / "b.nq"
    ds.serialize(a, format="trig")
    ds.serialize(b, format="nquads")
    assert compare.diff(a, b) == (frozenset(), frozenset())


def test_template_is_valid_trig() -> None:
    """The comparison template parses as TriG, which a future template interpreter relies on."""
    t = Dataset()
    t.parse(Path(__file__).parent.parent / "example" / "template.ttl", format="trig")
    iris = {str(s) for s, _, _, _ in t.quads()}
    assert "https://example.org/org/(id)" in iris
    assert "https://example.org/sector/URLIFY(SPLIT(sectors))" in iris


def test_split_values_stay_paired(ds: Dataset) -> None:
    for name in ("Energy", "Research", "OpenData"):
        assert len(objects(ds, EX["sector", name], SCHEMA.name)) == 1


def test_different_splits_combine() -> None:
    from rdfdsl import Prefix, split, subject

    ex = Prefix("urn:x:")
    a, b = split(["1", "2"]), split(["x", "y", "z"])
    paired = subject(ex["s", a]) >> ex.p << a << ex["t", a]
    crossed = subject(ex["s", a]) >> ex.p << b
    assert len(paired.triples) == 4
    assert len(crossed.triples) == 6
    assert len((subject(ex["s", a]) >> ex.p << [ex.u, ex.v]).triples) == 4
