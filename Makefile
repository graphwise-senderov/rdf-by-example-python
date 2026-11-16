# CSV to RDF example. `make build` writes example/out.trig, `make test` runs all tests.
PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
STAMP  := $(VENV)/.installed

.PHONY: all venv build test clean
all: build

$(STAMP): pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q -e '.[test]'
	touch $(STAMP)
venv: $(STAMP)

build: $(STAMP)
	$(PY) -m example.build example/out.trig

test: $(STAMP)
	$(PY) -m pytest -q

clean:
	rm -rf example/out.trig .pytest_cache build *.egg-info
