# RDF by Example in Python

A small Python DSL for turning table rows into RDF quads, with a worked example, a set of macro replacements, a comparison utility and tests. It depends only on rdflib. The approach was distilled from a production CSV-to-RDF migration.

## Quickstart

```sh
make build    # creates .venv, installs the package, writes example/out.trig
make test     # doctests and example tests (pytest)
```

Without Make: `python3 -m venv .venv && .venv/bin/pip install -e '.[test]'`, then `.venv/bin/python -m example.build` and `.venv/bin/pytest`.

| File | Content |
|---|---|
| `rdfdsl.py` | The DSL: `subject`, `graph`, `quads`, `Prefix`, literal makers, `@cell`, `Row`, `dataset` |
| `macros.py` | Python replacements for typical template macros |
| `compare.py` | Compares two RDF files as sets of canonical N-Quads |
| `example/organisations.csv`, `example/people.csv` | An invented dataset |
| `example/template.ttl` | The same mapping as an RDF by Example template, for comparison only |
| `example/mapping.py` | The row mappings in Python |
| `example/build.py` | Reads the CSV files, applies the mappings, writes `example/out.trig` |
| `tests/` | Doctests of every module, and checks of specific quads in the example output |

## 1. The RDF by Example idea

RDF by Example is an approach by Vladimir Alexiev ([rdf2rml](https://github.com/VladimirAlexiev/rdf2rml), in particular [doc/rdf2sparql.md](https://github.com/VladimirAlexiev/rdf2rml/blob/master/doc/rdf2sparql.md)). A modeller writes the target RDF once, as an example instance in Turtle or TriG, and marks the places where table cells go. The example is documentation (it shows what the output looks like), input for diagrams, and the source from which the transformation is generated. The modeller does not write SPARQL, RML or code.

For the organisations table of this package, the example reads (excerpt from `example/template.ttl`):

```turtle
graph <graph/organisations> {
  <org/(id)> a <CURIE(type)>;
    schema:name                "(name)";
    ex:sector                  <sector/URLIFY(SPLIT(sectors))>;
    schema:addressCountry      <country/IFNOT_EMPTY(country)>;
    schema:url                 <(homepage)>;
    schema:numberOfEmployees   "(employees)"^^xsd:integer.
}
```

`(column)` inserts a cell. `MACRO(column)` applies a macro to a cell, and macros nest.

## 2. The classic tool chain in brief

In the classic set-up the template is not executed directly:

- `rdf2sparql` reads the template line by line and generates a SPARQL CONSTRUCT (or UPDATE) query. Every placeholder becomes a variable, every macro call becomes a line in the WHERE clause, and every IRI or literal with placeholders becomes a `bind(iri(concat(...)))` or `bind(strdt(...))`.
- The C preprocessor expands the macro lines with a header of `#define` macros into SPARQL `bind(...)` expressions. For example `URLIFY(?name)` becomes a `replace(...)` chain bound to `?name_URLIFY`.
- A SPARQL engine that can read tables runs the query over the CSV file: SPARQL Anything, TARQL or Ontotext Refine.

The result is a short, readable model and a generated transformation. The cost is a tool chain of Perl, the C preprocessor and a Java SPARQL engine, plus a generated query in between that is hard to debug: an error in a macro or an empty cell usually produces no output instead of an error message.

## 3. The Python DSL and its three rules

`rdfdsl.py` keeps the idea that a mapping should look like its output, but writes it as a Python function per table (excerpt from `example/mapping.py`):

```python
def organisation(r: Row) -> tuple[Quad, ...]:
    sectors = split_comma(r.sectors)
    return graph(ORGANISATIONS,
        subject(EX["org", r.id])
        >> RDF.type << curie(r.type)
        >> SCHEMA.name << r.name
        >> EX.sector << EX["sector", urlify(sectors)]
        >> SCHEMA.addressCountry << EX["country", if_not_empty(r.country)]
        >> SCHEMA.url << iri(r.homepage)
        >> SCHEMA.numberOfEmployees << integer(r.employees),
        subject(EX["sector", urlify(sectors)])
        >> RDF.type << EX.Sector
        >> SCHEMA.name << en(sectors),
    )
```

- `subject(s) >> p << o1 << o2` describes a subject. `>>` selects the predicate and `<<` adds an object. Both operators have the same precedence and associate to the left, so a chain reads left to right like a Turtle predicate list.
- `graph(g, d1, d2, ...)` places descriptions into a named graph, and `quads(...)` concatenates blocks of quads.
- `Prefix("https://example.org/")` builds IRIs: `EX["org", "acme"]` joins the parts with `/`, and `EX.sector` names a fixed term.
- `lit`, `de`, `en`, `fr`, `it`, `integer`, `decimal`, `boolean`, `date` and `iri` make terms from cells. Typed literals keep their lexical form as it is.
- `Row` wraps a CSV row: `r.homepage` is the cell, or `None` if the cell is empty or the column is absent.

Three rules carry the semantics of the SPARQL templates:

1. `None` vanishes. An empty cell is `None`, and a subject, predicate, object or graph that is `None` emits nothing, as an unbound variable does in a SPARQL CONSTRUCT template. In the example, the empty `homepage` of `gruen` and the empty `email` of person `p2` produce no triple.
2. Lists fan out. A split cell is a list, and a list in any position emits one triple per element. `split_comma("Energy, Research, Open Data")` gives three `ex:sector` triples for `open-grid`. Values derived from the same split stay paired (see section 4), so the second description gives each sector exactly one name.
3. An invalid IRI is `None`. `Prefix` and `iri` return `None` for an IRI with a forbidden character such as a space, as SPARQL `iri()` fails on it, so rule 1 applies. The homepage `https://open grid.example.org` produces nothing.

The `@cell` decorator lifts a function on strings to cells: `None` passes through and lists are mapped element by element. All functions in `macros.py` use it, so `urlify(split_comma(...))` works on a list as `URLIFY(SPLIT(...))` did in the template.

## 4. Template and Python side by side

The people table, as a template (`example/template.ttl`):

```turtle
graph <graph/people> {
  <person/(id)> a schema:Person;
    schema:givenName           "(given_name)";
    schema:familyName          "(family_name)";
    ex:handle                  "URLIFY(given_name)DASH_IF(URLIFY(family_name))";
    schema:worksFor            <org/(organisation)>;
    schema:roleName            "SPLIT_SEMI(roles)"@en;
    schema:email               "(email)".
}
```

And in Python (`example/mapping.py`):

```python
def person(r: Row) -> tuple[Quad, ...]:
    handle = urlify(r.given_name) and urlify(r.given_name) + dash_if(urlify(r.family_name))
    return graph(PEOPLE,
        subject(EX["person", r.id])
        >> RDF.type << SCHEMA.Person
        >> SCHEMA.givenName << r.given_name
        >> SCHEMA.familyName << r.family_name
        >> EX.handle << handle
        >> SCHEMA.worksFor << EX["org", r.organisation]
        >> SCHEMA.roleName << en(split_semi(r.roles))
        >> SCHEMA.email << r.email,
    )
```

The correspondence is line by line. Output for two rows (from `example/out.trig`):

```turtle
<https://example.org/person/p2> a schema:Person ;
    ex:handle "Juergen-Mueller" ;
    schema:familyName "Müller" ;
    schema:givenName "Jürgen" ;
    schema:roleName "Site Manager"@en ;
    schema:worksFor <https://example.org/org/gruen> .

<https://example.org/person/p5> a schema:Person ;
    ex:handle "Sofia" ;
    schema:email "sofia@wasser.example.org" ;
    schema:givenName "Sofia" ;
    schema:roleName "Engineer"@en ;
    schema:worksFor <https://example.org/org/wasser> .
```

Person `p2` has no `schema:email` (empty cell), and person `p5` has no family name, so the handle has no dash.

Split values stay paired, as in a template. In `<sector/URLIFY(SPLIT(sectors))> schema:name "SPLIT(sectors)"@en`, each sector IRI gets its own name, and the DSL does the same: `split_comma` returns a `Split`, a list with an identity key, and every value derived from it element by element (through `@cell` functions such as `urlify` and `en`, or through `Prefix`) keeps that key. When a triple combines values, element *i* of a split is only combined with element *i* of the same split, so `subject(EX["sector", urlify(sectors)]) >> SCHEMA.name << en(sectors)` gives one name per sector, not every combination. Values from different splits, or plain lists, still combine in every way, as two separate splits do in SPARQL. This is the better design regardless of templates: reusing a split value means reusing the same element, and a cross product of a list with itself is almost never intended.

## 5. Macros as Python functions

Each macro becomes a small pure function with doctests in `macros.py`:

| Template macro | Python function | Effect |
|---|---|---|
| `URLIFY(x)` | `urlify(x)` | Transliterate German umlauts and ß, then keep letters and digits: `Grün & Söhne GmbH` to `GruenSoehneGmbH` |
| `SPLIT(x)` | `split_comma(x)` | Split a multi-valued cell on commas |
| `SPLIT_SEMI(x)` | `split_semi(x)` | Split on semicolons |
| `IFNOT_EMPTY(x)` | `if_not_empty(x)` | `None` for placeholders such as `n/a` |
| `CURIE(x)` | `curie(x)` | Expand a prefixed name such as `schema:NGO` with known prefixes |
| `DASH_IF(x)` | `dash_if(x)` | `-x` if there is a value, else the empty string |

Concatenations that a template writes inline become ordinary expressions, or a named helper with a docstring when they grow. Since the functions are plain Python, they can be unit tested, reused across tables, and read without knowing the C preprocessor.

## 6. Staying in Python end to end

`example/build.py` reads the CSV files with the standard `csv` module, applies the mappings row by row, collects the quads into an rdflib `Dataset` and writes TriG. There is no generated query, no preprocessor and no JVM: a mistake is a Python exception with a traceback, and a debugger can stop inside a mapping for a given row. Table preparation that would otherwise be a separate script (splitting, renaming columns, joining tables) can be written in the same language, before the mapping.

## 7. Verifying against a reference pipeline

When the DSL replaces an existing pipeline, equivalence should be measured, not assumed. The approach that worked in practice:

1. Run the existing pipeline on the same inputs into a reference directory.
2. Run the Python pipeline into an output directory.
3. Parse both sides with rdflib and write every quad in a canonical N-Quads form, then compare the two sets per file: quads missing from the new output, and extra quads in it.

`compare.py` implements step 3 (`python compare.py new.trig reference.trig`). It parses literals without normalisation, so lexical forms are compared as written, and applies only two canonicalisations: `"x"^^xsd:string` equals the plain literal `"x"`, and `xsd:decimal` compares by value. It does not canonicalise blank nodes, so it suits outputs that use IRIs only.

Equality includes the quirks of the old pipeline. Reproducing them on purpose, documenting each, and fixing them after the cut-over with a visible diff keeps the switch itself free of surprises.

## 8. Future direction: a template interpreter

The DSL makes the Python mapping the source of truth, and the Turtle template becomes documentation. The next step is to keep the template as the source and run it directly:

- rdflib parses the template as TriG. This works because parentheses, commas and underscores are legal inside IRIs; `tests/test_example.py` checks that `example/template.ttl` parses and keeps IRIs such as `https://example.org/sector/URLIFY(SPLIT(sectors))`.
- A small parser reads each IRI and literal into constant text, `(column)` placeholders and nested macro calls.
- Macro calls are evaluated through a registry of Python functions under the macro names (`URLIFY` to `urlify`, `SPLIT` to `split_comma`, and so on).
- The parsed template is compiled to the DSL (`subject >> p << o`, `graph`, `Prefix`), so that the three rules above are reused instead of reimplemented. A split value used several times in one triple must stay correlated, as in SPARQL.
- Row filters that templates express as extra annotations become named Python filters.
- `compare.py` verifies the interpreter against the output of the classic tool chain before anything is switched.

## Licence

This package is released under the MIT License; see [LICENSE](LICENSE).
