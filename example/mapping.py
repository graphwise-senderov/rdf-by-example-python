"""Row mappings for the example: the Python equivalent of ``template.ttl``."""

from rdflib import RDF

from macros import curie, dash_if, if_not_empty, split_comma, split_semi, urlify
from rdfdsl import Prefix, Quad, Row, date, en, graph, integer, iri, quads, subject

EX = Prefix("https://example.org/")
SCHEMA = Prefix("https://schema.org/")

ORGANISATIONS = EX["graph", "organisations"]
PEOPLE = EX["graph", "people"]

PREFIXES = {"ex": EX.base, "schema": SCHEMA.base, "xsd": "http://www.w3.org/2001/XMLSchema#"}


def organisation(r: Row) -> tuple[Quad, ...]:
    """An organisation, and one ``ex:Sector`` per value of the multi-valued ``sectors`` cell."""
    sectors = split_comma(r.sectors) or []
    return quads(
        graph(ORGANISATIONS,
            subject(EX["org", r.id])
            >> RDF.type << curie(r.type)
            >> SCHEMA.name << r.name
            >> SCHEMA.alternateName << urlify(r.name)
            >> EX.sector << EX["sector", urlify(sectors)]
            >> SCHEMA.addressCountry << EX["country", if_not_empty(r.country)]
            >> SCHEMA.url << iri(r.homepage)
            >> SCHEMA.numberOfEmployees << integer(r.employees)
            >> SCHEMA.foundingDate << date(r.founded)),
        *(graph(ORGANISATIONS,
            subject(EX["sector", urlify(name)])
            >> RDF.type << EX.Sector
            >> SCHEMA.name << en(name))
          for name in sectors),
    )


def person(r: Row) -> tuple[Quad, ...]:
    """A person, the organisation they work for, and their roles."""
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
