"""pktlib.audit and `pktlib audit`: problems are lines of text that know their devices."""

import subprocess
import sys

import pktlib
from pktlib import Problem, audit


def broken(net):
    net.pc("A", ip="10.0.0.5/24", gateway="10.0.0.1")
    net.pc("B", ip="10.0.0.5/24", gateway="10.0.0.1")
    return net


def test_a_problem_is_its_sentence_and_names_its_devices(net):
    found = audit(broken(net))
    dup = next(p for p in found if "on more than one port" in p)
    assert isinstance(dup, Problem) and isinstance(dup, str)
    assert dup == "10.0.0.5 is on more than one port: A.FastEthernet0, B.FastEthernet0"
    assert dup.devices == ("A", "B")


def test_cli_audit_exit_codes(tmp_path, net):
    clean, bad = tmp_path / "clean.pkt", tmp_path / "bad.pkt"
    pktlib.new(seed=1).save(clean)
    broken(net).save(bad)
    ok = subprocess.run([sys.executable, "-m", "pktlib", "audit", str(clean)], capture_output=True, text=True)
    assert ok.returncode == 0 and "nothing found" in ok.stdout
    run = subprocess.run([sys.executable, "-m", "pktlib", "audit", str(bad)], capture_output=True, text=True)
    assert run.returncode == 1 and "  x 10.0.0.5 is on more than one port" in run.stdout


def test_a_switch_only_lab_needs_no_gateway(net):
    """Found by the CCNA examples: a PC with no gateway was flagged even with no router to point at."""
    sw = net.switch("S")
    for i in (1, 2):
        net.pc(f"P{i}", ip=f"10.0.0.{i}/24")["fa0"].connect(sw[f"fa0/{i}"])
    assert audit(net) == []
    r = net.router("R", "2911")
    r["g0/0"].connect(sw["fa0/3"])
    r["g0/0"].address = "10.0.0.254/24"
    assert any("P1 has no default gateway" in p for p in audit(net))


def test_cli_audits_several_files(tmp_path, net):
    clean, bad = tmp_path / "clean.pkt", tmp_path / "bad.pkt"
    pktlib.new(seed=1).save(clean)
    broken(net).save(bad)
    run = subprocess.run(
        [sys.executable, "-m", "pktlib", "audit", str(clean), str(bad), str(tmp_path / "missing.pkt")],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "nothing found" in run.stdout and "on more than one port" in run.stdout
    assert "1 of 3 files clean" in run.stdout and "missing.pkt" in run.stderr


def test_a_home_router_lan_address_is_a_gateway(net):
    """Found by the showcase examples: a PC pointed at a Linksys's 192.168.0.1 was flagged."""
    wrt = net.add_device("HOME", "Linksys-WRT300N")
    pc = net.pc("PC", ip="192.168.0.10/24", gateway="192.168.0.1")
    pc["fa0"].connect(wrt["Ethernet 1"])
    assert not any("gateway" in p for p in audit(net))


def test_network_and_broadcast_addresses_on_router_ports(net):
    """Packet Tracer 8.2 drops both when it loads the file (27 Oct 2026: a 2911 given
    10.0.0.0/24, and the CCNA ipv6 example's R3 given 10.0.23.3/30, came up with no
    address). A /31 has no network or broadcast address, so it's left alone."""
    r = net.router("R", "2911")
    r["g0/0"].address = "10.0.0.0/24"
    r["g0/1"].address = "10.0.23.3/30"
    r["g0/2"].address = "10.0.31.1/31"
    found = [p for p in audit(net) if "address of" in p]
    assert found == [
        "R.GigabitEthernet0/0: 10.0.0.0 is the network address of 10.0.0.0/24; "
        "Packet Tracer drops it, so the port has no address",
        "R.GigabitEthernet0/1: 10.0.23.3 is the broadcast address of 10.0.23.0/30; "
        "Packet Tracer drops it, so the port has no address",
    ]
    assert found[0].devices == ("R",)
