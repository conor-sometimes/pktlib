"""Every example and stress script, built with a fixed seed, writes exactly the
XML it wrote when tests/golden.json was recorded.

This is the guard for refactors: a change to how the API looks must not change
a byte of what Packet Tracer gets. When a change is meant to alter the output,
look at the diff of the decoded files first (pktlib decode), then re-record:

    PKTLIB_UPDATE_GOLDEN=1 uv run pytest -n0 tests/test_golden.py
"""

import contextlib
import hashlib
import json
import os
import random
import runpy
import sys
import types
from pathlib import Path

import pytest

import pktlib
import pktlib._model

ROOT = Path(__file__).parents[1]
GOLDEN = Path(__file__).parent / "golden.json"
UPDATE = os.environ.get("PKTLIB_UPDATE_GOLDEN") == "1"

SCRIPTS = sorted(list((ROOT / "examples").rglob("*.py")) + list((ROOT / "stress").glob("*/[rs][tw][0-9]*.py")))
ARGV = {"practice_lab.py": ["42"]}


def _seeded_random() -> types.ModuleType:
    """random, except that Random() with no seed is Random(0)."""
    shim = types.ModuleType("random")
    shim.__dict__.update(random.__dict__)
    setattr(shim, "Random", lambda seed=None: random.Random(0 if seed is None else seed))  # noqa: B010
    return shim


def _build(script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    saved: dict[str, str] = {}

    def save(self: pktlib.Network, path: str | Path) -> None:
        saved[Path(path).name] = hashlib.sha256(self.to_xml()).hexdigest()

    monkeypatch.setattr(pktlib._model, "random", _seeded_random())
    monkeypatch.setattr(pktlib.Network, "save", save)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(script.parent))
    monkeypatch.setattr(sys, "argv", [str(script), *ARGV.get(script.name, [])])
    with contextlib.suppress(SystemExit):
        runpy.run_path(str(script), run_name="__main__")
    return saved


def _key(script: Path) -> str:
    return script.relative_to(ROOT).as_posix()


@pytest.fixture(scope="module")
def golden():
    if UPDATE and os.environ.get("PYTEST_XDIST_WORKER"):
        pytest.fail("re-record with one process: PKTLIB_UPDATE_GOLDEN=1 uv run pytest -n0 tests/test_golden.py")
    recorded = {} if UPDATE or not GOLDEN.exists() else json.loads(GOLDEN.read_text())  # re-recording starts fresh
    yield recorded
    if UPDATE:
        GOLDEN.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n")


@pytest.mark.parametrize("script", SCRIPTS, ids=_key)
def test_output_unchanged(script, golden, tmp_path, monkeypatch, capsys):
    saved = _build(script, tmp_path, monkeypatch)
    assert saved, f"{script.name} saved nothing"
    if UPDATE:
        golden[_key(script)] = saved
    assert saved == golden.get(_key(script)), "output changed; see this module's docstring"
