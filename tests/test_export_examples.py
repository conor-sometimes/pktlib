"""to_python on every example: the rebuilt network has everything the original has."""

from __future__ import annotations

import contextlib
import random
import runpy
import sys
import types
import warnings
from pathlib import Path

import pytest

import pktlib
import pktlib._model

ROOT = Path(__file__).parents[1]
SCRIPTS = sorted((ROOT / "examples").rglob("*.py"))
ARGV = {"practice_lab.py": ["42"]}


def _networks(script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[pktlib.Network]:
    nets: list[pktlib.Network] = []
    shim = types.ModuleType("random")
    shim.__dict__.update(random.__dict__)
    setattr(shim, "Random", lambda seed=None: random.Random(0 if seed is None else seed))  # noqa: B010
    monkeypatch.setattr(pktlib._model, "random", shim)
    real_save = pktlib.Network.save
    monkeypatch.setattr(pktlib.Network, "save", lambda self, path: (nets.append(self), real_save(self, path)))
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(script.parent))
    monkeypatch.setattr(sys, "argv", [str(script), *ARGV.get(script.name, [])])
    with warnings.catch_warnings(), contextlib.suppress(SystemExit):
        warnings.simplefilter("ignore", pktlib.PktWarning)
        runpy.run_path(str(script), run_name="__main__")
    return nets


def _what_matters(net: pktlib.Network) -> dict[str, object]:
    out: dict[str, object] = {
        "profile": net.profile,
        "pdus": sorted(net.pdus),
        "notes": sorted((n.text, n.xy) for n in net.notes),
        "shapes": sorted((s.kind, s.box, s.outline or "", s.fill or "") for s in net.shapes),
        "links": sorted((tuple(sorted(link.ends)), link.cable) for link in net.links),
    }
    for d in net:
        out[d.name] = {
            "model": d.model,
            "xy": d.xy,
            "modules": sorted((s.path, s.model) for s in d.slots if s.removable and s.model),
            "addresses": {p.name: p.address for p in d},
            "gateway": d.gateway,
            "dhcp": d.dhcp,
            "vlans": dict(d.vlans),
            "config": pktlib._iosconfig.interesting_config(d.running_config) if d.has_ios else [],
        }
    return out


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_to_python_keeps_everything(script, tmp_path, monkeypatch):
    for net in _networks(script, tmp_path, monkeypatch):
        code = pktlib.to_python(net).replace("net.save('out.pkt')", "")
        scope: dict = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", pktlib.PktWarning)
            exec(compile(code, "<export>", "exec"), scope)
        want, got = _what_matters(net), _what_matters(scope["net"])
        for key in want:
            assert got.get(key) == want[key], f"{script.name}: {key} differs after to_python"
