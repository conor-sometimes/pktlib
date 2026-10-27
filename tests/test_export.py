"""to_python: any .pkt -> a script that rebuilds it. Run the script, export again, same text."""

import contextlib
import warnings

import pytest

import pktlib
from pktlib._model import SPEC


def run_script(src: str, out_path) -> pktlib.Network:
    src = src.replace("net.save('out.pkt')", f"net.save({str(out_path)!r})")
    exec(compile(src, "<export>", "exec"), {})
    return pktlib.load(out_path)


def test_routed_round_trip_is_exact(routed, tmp_path):
    first = pktlib.to_python(routed)
    rebuilt = run_script(first, tmp_path / "r.pkt")
    assert pktlib.to_python(rebuilt) == first


def test_rebuilt_routed_has_the_same_network(routed, tmp_path):
    rebuilt = run_script(pktlib.to_python(routed), tmp_path / "r.pkt")
    assert {(*l.ends, l.cable, l.dce) for l in rebuilt.links} == {(*l.ends, l.cable, l.dce) for l in routed.links}
    for d in routed.devices:
        r = rebuilt.device(d.name)
        assert (r.kind, r.model, r.xy) == (d.kind, d.model, d.xy)
        assert {n: p.address for n, p in r.ports.items()} == {n: p.address for n, p in d.ports.items()}
    assert len(rebuilt.shapes) == len(routed.shapes) and len(rebuilt.notes) == len(routed.notes)


def test_export_is_valid_python_for_a_built_network(tmp_path):
    n = pktlib.new(seed=5)
    r = n.router("Core-1", "2911", at=(1, 2))
    s = n.switch("class", at=(3, 4))  # a Python keyword as a device name
    p = n.pc("first", ip="10.0.0.2/24", gateway="10.0.0.1")
    r["g0/0"].connect(s["fa0/1"])
    s["fa0/2"].connect(p["fa0"])
    r["g0/0"].address = "10.0.0.1/24"
    n.note("hi", at=(0, 0))
    src = pktlib.to_python(n)
    assert not any(line.startswith("class = ") for line in src.splitlines())
    rebuilt = run_script(src, tmp_path / "x.pkt")
    assert pktlib.to_python(rebuilt) == src


def test_unverified_devices_export_with_the_flag(monkeypatch):
    from pktlib._model import SPEC

    monkeypatch.setitem(SPEC, "Meraki-MX65W", {**SPEC["Meraki-MX65W"], "verified": False})
    n = pktlib.new(seed=6)
    n.add_device("M", "Meraki-MX65W", unverified=True)
    assert "unverified=True" in pktlib.to_python(n)


def _round_trips(net: pktlib.Network) -> None:
    script = pktlib.to_python(net)
    scope: dict = {}
    exec(compile(script.replace("net.save('out.pkt')", ""), "<export>", "exec"), scope)
    assert pktlib.to_python(scope["net"]) == script


@pytest.mark.parametrize("model", pktlib.models())
def test_every_model_round_trips_with_every_card_it_takes(model):
    """Found by the soak: to_python left out fitted modules, so a rebuilt Server-PT had no
    second NIC and a cable to it failed; and a model's default config blocks (an ASA's
    policy-map) were exported whole, so replaying them repeated their lines."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pktlib.PktWarning)
        net = pktlib.new(seed=1)
        net.add_device("D0", model)
        _round_trips(net)
        for card in SPEC[model].get("accepts") or []:
            net = pktlib.new(seed=1)
            d = net.add_device("D0", model)
            try:
                d.add_module(card)
            except pktlib.PktError:
                continue  # no free slot of that kind, or no template for the card yet
            free = [p for p in d if p.link is None and p.type != "eBluetooth"]
            with contextlib.suppress(pktlib.PktError, IndexError):
                free[-1].connect(net.pc("PC")["fa0"])
            _round_trips(net)
