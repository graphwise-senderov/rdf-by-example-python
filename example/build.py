"""Build ``out.trig`` from the example CSV files.

Run from the repository root: ``python -m example.build [output]``.
"""

import csv
import sys
from collections.abc import Callable, Iterable, Iterator
from itertools import chain
from pathlib import Path

from rdflib import Dataset

from example.mapping import PREFIXES, organisation, person
from rdfdsl import Quad, Row, dataset

HERE = Path(__file__).parent

TARGETS: tuple[tuple[str, Callable[[Row], Iterable[Quad]]], ...] = (
    ("organisations.csv", organisation),
    ("people.csv", person),
)
"""Input table and row mapping, in build order."""


def rows(path: Path) -> Iterator[Row]:
    """Rows of a UTF-8 CSV file with a header line."""
    with path.open(encoding="utf-8", newline="") as f:
        yield from map(Row, csv.DictReader(f))


def build(input_dir: Path = HERE) -> Dataset:
    """Apply every mapping to every row of its table and collect the quads."""
    return dataset(
        chain.from_iterable(mapping(row) for table, mapping in TARGETS for row in rows(input_dir / table)),
        PREFIXES,
    )


def main(argv: list[str]) -> None:
    output = Path(argv[1]) if len(argv) > 1 else HERE / "out.trig"
    ds = build()
    ds.serialize(output, format="trig")
    print(f"{output}: {sum(1 for _ in ds.quads())} quads")


if __name__ == "__main__":
    main(sys.argv)
