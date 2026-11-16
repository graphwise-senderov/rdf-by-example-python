"""Run the doctests of every module."""

import doctest

import pytest

import compare
import macros
import rdfdsl


@pytest.mark.parametrize("module", [rdfdsl, macros, compare], ids=lambda m: m.__name__)
def test_doctests(module) -> None:
    result = doctest.testmod(module)
    assert result.attempted > 0
    assert result.failed == 0
