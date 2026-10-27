# pktlib recipes. Everything runs through uv; nothing to install by hand.
# `just` on its own lists them.

default:
    @just --list

# the whole test suite on every core, in a random order (~1 minute), golden check included
test *args:
    uv run pytest -q {{args}}

# lint and type-check: ruff, ty on everything, then the package as users' checkers see it
# (mypy --strict, pyright, and pyright's check that every public name is typed and documented)
lint:
    uv run ruff check
    uv run ruff format --check
    uv run ty check
    uv run mypy --strict src/pktlib
    uv run pyright src/pktlib
    uv run pyright --verifytypes pktlib --ignoreexternal
    uvx zizmor@1.31.1 --offline .github

# every check a commit needs: lint, then the whole test suite
check: lint test

# the tests with line and branch coverage of the package
cov:
    uv run pytest -q --cov --cov-report=term

# mutation testing: plant small bugs in the package and see which no test catches (slow; `just mutants` lists survivors)
mutate *names:
    uv run mutmut run {{names}}

# the bugs mutmut planted that no test caught, with diffs: `uv run mutmut show NAME` for one
mutants:
    uv run mutmut results

# tests minus the slow property-based ones
quick:
    uv run pytest -q -k "not fuzz"

# the random tests with 20 times the examples (a few minutes)
fuzz:
    PKTLIB_SCALE=20 uv run pytest -q -k "fuzz or round_trip or flip or properties or stateful"

# every random test on every core but two, for HOURS (default 1); counts the cases, keeps failure logs in soak/
soak hours="1":
    uv run python scripts/soak.py --hours {{hours}}

# one test file or pattern, verbose: `just t spec`
t pattern:
    uv run pytest -v -k "{{pattern}}"

# build every example into out/examples/ and audit each (a student file, and solar_system's Pluto, fail on purpose)
examples:
    uv run python scripts/examples.py build

# rewrite examples/README.md from the examples' docstrings
examples-index:
    uv run python scripts/examples.py index

# build one example into out/: `just example ospf_ring 8 2`
example name *args:
    mkdir -p out
    cd out && uv run python "$(find ../examples -name '{{name}}.py')" {{args}}

# lint a .pkt: duplicate IPs/MACs, bad gateways, shut cabled ports, missing clock rates
audit file:
    uv run pktlib audit "{{file}}"

# devices, ports, links and addresses in a .pkt
info file:
    uv run pktlib info "{{file}}"

# a .pkt as a Python script that rebuilds it
dump file out="":
    uv run pktlib dump "{{file}}" {{out}}

# a .pkt as Packet Tracer's raw XML
decode file out="":
    uv run pktlib decode "{{file}}" {{out}}

# re-extract device templates from scripts/sources/*.pkt (after re-saving them in Packet Tracer)
templates:
    uv run python scripts/make_templates.py

# rebuild src/pktlib/spec/devices.json from the templates; review the diff before committing
spec:
    uv run python scripts/make_spec.py

# both, then the tests that hold the library to the spec
refresh: templates spec
    uv run pytest -q tests/test_spec.py

# models pktlib can create
models:
    uv run python -c "import pktlib; print('\n'.join(pktlib.models()))"

# rebuild the stress-test networks in stress/ and audit them all
stress:
    for f in stress/switching/sw*.py stress/routing/rt*.py; do uv run python "$f" > /dev/null; done
    for f in stress/*/*.pkt; do uv run pktlib audit "$f"; done
