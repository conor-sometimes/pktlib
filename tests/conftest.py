import json
import os
from importlib import resources
from pathlib import Path

import pytest
from hypothesis import settings

import pktlib

# PKTLIB_SCALE multiplies how many examples every random test runs: 1 for `just test`,
# more for `just fuzz` and scripts/soak.py. Tests set their own count with examples(n).
SCALE = max(1, int(os.environ.get("PKTLIB_SCALE", "1")))
settings.register_profile("scaled", max_examples=100 * SCALE, deadline=None if SCALE > 1 else 200)
settings.load_profile("scaled")


def examples(n: int) -> int:
    """How many examples a random test runs: n, times PKTLIB_SCALE."""
    return n * SCALE


FIXTURES = Path(__file__).parent / "fixtures"
ROUTED = FIXTURES / "routed.pkt"
SOURCES = Path(__file__).parents[1] / "scripts" / "sources"


@pytest.fixture(scope="session")
def routed_bytes() -> bytes:
    return ROUTED.read_bytes()


@pytest.fixture(scope="session")
def routed_xml(routed_bytes) -> bytes:
    return pktlib.decode(routed_bytes)


@pytest.fixture
def routed(routed_bytes) -> pktlib.Network:
    return pktlib.Network.from_bytes(routed_bytes, seed=1)


@pytest.fixture
def net() -> pktlib.Network:
    return pktlib.new(seed=1)


@pytest.fixture(scope="session")
def spec() -> dict:
    return json.loads(resources.files("pktlib").joinpath("spec").joinpath("devices.json").read_text("utf-8"))
