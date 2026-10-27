"""Every example builds, and the audit finds nothing wrong with what they build.
(Each was also opened in Packet Tracer 8.2 and pinged across; see README.)"""

import runpy
import sys
from pathlib import Path

import pytest

import pktlib
from pktlib import audit

EXAMPLES = Path(__file__).parents[1] / "examples"


def example(name: str) -> Path:
    """An example script by file name, whichever folder of examples/ it's in."""
    (found,) = EXAMPLES.rglob(name)
    return found


@pytest.mark.parametrize(
    "script,out,argv",
    [
        ("ospf_ring.py", "ospf_ring.pkt", []),
        ("router_on_a_stick.py", "router_on_a_stick.pkt", []),
        ("datacenter.py", "datacenter.pkt", []),
        ("enterprise.py", "enterprise.pkt", []),
        ("datacentres.py", "datacentres.pkt", []),
    ],
)
def test_example_builds_clean(script, out, argv, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [script, *argv])
    runpy.run_path(str(example(script)), run_name="__main__")
    net = pktlib.load(tmp_path / out)
    assert audit(net) == []


@pytest.mark.parametrize("n", ["3", "8"])
def test_ospf_ring_sizes(n, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["ospf_ring.py", n, "1"])
    runpy.run_path(str(example("ospf_ring.py")), run_name="__main__")
    net = pktlib.load(tmp_path / "ospf_ring.pkt")
    assert sum(1 for d in net.devices if d.kind == "Router") == int(n)
    assert audit(net) == []


def test_practice_lab_is_seeded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["practice_lab.py", "42"])
    runpy.run_path(str(example("practice_lab.py")), run_name="__main__")
    first = (tmp_path / "practice_lab_answers.txt").read_text()
    runpy.run_path(str(example("practice_lab.py")), run_name="__main__")
    assert (tmp_path / "practice_lab_answers.txt").read_text() == first
    problems = audit(pktlib.load(tmp_path / "practice_lab.pkt"))
    assert problems and all("shut down" in p or "isn't any router" in p for p in problems)  # routers left for you


def test_audit_catches_problems(routed):
    routed.device("PC1").set_ip("10.1.0.10/24", "10.1.0.99")
    routed.device("PC3").set_ip("10.1.0.10/24", "10.1.0.1")
    found = audit(routed)
    assert any("on more than one port" in p for p in found)
    assert any("PC1's gateway 10.1.0.99" in p for p in found)


def test_datacenter_channel_is_laid_out_as_packet_tracer_saves_it(tmp_path, monkeypatch):
    """Checked in Packet Tracer 8.2 on 25 Oct: Po1(SU) with both members, OSPF
    FULL between the cores, HSRP stable, phones registered. The layout is what
    makes that work: members' channel-group in their own block, Port-channel1
    ahead of the physical ports, one block per interface."""
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(example("datacenter.py")), run_name="__main__")
    net = pktlib.load(tmp_path / "datacenter.pkt")
    for name in ("CORE1", "CORE2"):
        rc = net.device(name).running_config
        po = rc.index("interface Port-channel1")
        assert po < next(i for i, l in enumerate(rc) if l.startswith("interface GigabitEthernet"))
        for port in ("GigabitEthernet1/0/23", "GigabitEthernet1/0/24"):
            assert rc.count(f"interface {port}") == 1
            i = rc.index(f"interface {port}")
            assert " channel-group 1 mode active" in rc[i : rc.index("!", i)]
        assert "router ospf 1" in rc


@pytest.mark.parametrize(
    "script,out",
    [
        ("router_on_a_stick.py", "router_on_a_stick.pkt"),
        ("datacenter.py", "datacenter.pkt"),
        ("enterprise.py", "enterprise.pkt"),
    ],
)
def test_examples_write_each_interface_once(script, out, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [script])
    runpy.run_path(str(example(script)), run_name="__main__")
    for d in pktlib.load(tmp_path / out).devices:
        if d.has_ios:
            headers = [l for l in d.running_config if l.startswith("interface ")]
            assert len(headers) == len(set(headers)), d.name


def test_audit_flags_config_packet_tracer_refuses():
    net = pktlib.new(seed=41)
    r = net.router("R", "2911")
    with pytest.warns(pktlib.PktWarning, match="refused by Packet Tracer"):
        r.config("router ospf 1\n default-information originate metric 10")
    found = audit(net)
    assert any("default-information originate metric 10" in f and "refused" in f for f in found)


def test_solar_system_is_clean_apart_from_pluto(tmp_path, monkeypatch):
    """Pluto has no link and a gateway nobody owns, on purpose. The audit
    should notice that and nothing else."""
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(example("solar_system.py")), run_name="__main__")
    net = pktlib.load(tmp_path / "solar_system.pkt")
    assert audit(net) == ["PLUTO's gateway 10.9.0.1 isn't any router's address"]
    assert len([d for d in net.devices if d.kind == "Router"]) == 9  # 8 planets + mission control


def test_datacentres_full_mesh(tmp_path, monkeypatch):
    """Five sites, every pair linked by serial; checked in Packet Tracer 8.2 on
    25 Oct: DUBLIN-BR FULL with all four other borders, pings to PARIS-WEB1
    and AMSTERDAM-DB2."""
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(example("datacentres.py")), run_name="__main__")
    net = pktlib.load(tmp_path / "datacentres.pkt")
    borders = [d.name for d in net.devices if d.name.endswith("-BR")]
    assert len(borders) == 5
    mesh = {frozenset(a for a, _ in l.ends) for l in net.links if l.cable == "serial"}
    assert len(mesh) == 10 and all(len(pair) == 2 and pair <= set(borders) for pair in mesh)
    assert all(net.device(b).modules == ["HWIC-2T", "HWIC-2T"] for b in borders)
    assert net.duplicate_macs() == {} and net.duplicate_link_locals() == {}


def test_audit_flags_the_gigabit_only_access_point_card():
    """AccessPoint-PT-AC ships with PT-REPEATER-NM-1CGE, which stays red to any
    FastEthernet port in Packet Tracer 8.2 (cross or straight) and green to a
    switch's gigabit port. With PT-REPEATER-NM-1CFE fitted it links to a PC on
    a straight cable."""
    net = pktlib.new(seed=81)
    ap, pc = net.add_device("AC", "AccessPoint-PT-AC"), net.pc("P")
    assert ap["Port 0"].module == "PT-REPEATER-NM-1CGE"
    ap["Port 0"].connect(pc["fa0"])
    assert any("only links to gigabit ports" in p and "PT-REPEATER-NM-1CFE" in p for p in audit(net))
    ap["Port 0"].disconnect()
    slot = next(s for s in ap.slots if s.model == "PT-REPEATER-NM-1CGE")
    ap.remove_module(slot.path)
    ap.add_module("PT-REPEATER-NM-1CFE", slot=slot.path)
    link = ap["Port 0"].connect(pc["fa0"])
    assert link.cable == "straight" and not any("gigabit" in p for p in audit(net))
    sw = net.switch("SW")
    ap2 = net.add_device("AC2", "AccessPoint-PT-AC")
    ap2["Port 0"].connect(sw["g0/1"])
    assert not any("AC2" in p for p in audit(net))


def test_audit_flags_shared_ospf_router_ids():
    net = pktlib.new(seed=115)
    for name in ("A", "B"):
        net.router(name, "2911").config("router ospf 1\n router-id 1.1.1.1")
    assert "OSPF router-id 1.1.1.1 is on more than one router: A, B" in audit(net)
