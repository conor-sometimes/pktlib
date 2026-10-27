"""Getting around a network by objects: cables, peers, neighbours, interface settings."""

import pytest

import pktlib
from pktlib import End, Interface, Pdu, PktError, RsaKey


@pytest.fixture
def lan(net):
    r = net.router("R1", "2911", at=(100, 100))
    sw = net.switch("S1", at=(100, 200))
    pc = net.pc("PC1", at=(100, 300), ip="10.0.0.5/24")
    pc["fa0"].connect(sw["fa0/1"])
    sw["g0/1"].connect(r["g0/0"])
    return net


def test_links_join_ports(lan):
    link = lan["PC1"]["fa0"].link
    assert link is not None
    assert link.ports == (lan["PC1"]["fa0"], lan["S1"]["fa0/1"])
    assert link.other(lan["PC1"]["fa0"]) == lan["S1"]["fa0/1"]
    assert link.ends == (End("PC1", "FastEthernet0"), End("S1", "FastEthernet0/1"))
    with pytest.raises(PktError, match="isn't on this cable"):
        link.other(lan["R1"]["g0/0"])


def test_peer_and_neighbors(lan):
    assert lan["S1"]["g0/1"].peer == lan["R1"]["g0/0"]
    assert lan["R1"]["g0/1"].peer is None
    assert lan["S1"].neighbors == [lan["PC1"], lan["R1"]]
    assert len(lan["S1"].links) == 2 and lan["R1"].links == [lan["R1"]["g0/0"].link]


def test_interface_settings_without_parsing_config(lan):
    sw = lan["S1"]
    sw.config("interface fa0/2\n switchport mode access\n switchport access vlan 10\n switchport voice vlan 20")
    sw.config("interface fa0/3\n sw acc vl 30")
    assert sw["fa0/2"].mode == "access" and sw["fa0/2"].access_vlan == 10 and sw["fa0/2"].voice_vlan == 20
    assert sw["fa0/3"].access_vlan == 30
    assert sw["fa0/4"].mode is None and sw["fa0/4"].access_vlan is None
    r = lan["R1"]
    r.config("interface g0/1\n description uplink to ISP")
    assert r["g0/1"].setting("description") == "description uplink to ISP"
    assert r["g0/1"].setting("clock rate") is None


def test_records_have_field_names(lan):
    r = lan["R1"]
    r["g0/1"].address = "10.1.0.1/24"
    assert r.interfaces["GigabitEthernet0/1"] == Interface("10.1.0.1/24", up=True)
    assert r.interfaces["GigabitEthernet0/1"].address == "10.1.0.1/24"
    lan.ping("PC1", "R1", ip="10.1.0.1")
    assert lan.pdus[0] == Pdu("Scenario 0", "PC1", "R1", "10.1.0.1") and lan.pdus[0].destination == "R1"
    r.config("ip domain-name lab.local")
    r.generate_rsa_key(1024)
    assert r.rsa_key == RsaKey("R1.lab.local", 1024) and r.rsa_key.bits == 1024


def test_reprs_say_what_they_are(lan):
    shape = lan.rectangle(0, 0, 100, 50, outline="red")
    note = lan.note("Core", at=(10, 20))
    assert repr(shape) == "<Shape rectangle (0, 0)-(100, 50) outline #d62828>"
    assert repr(note) == "<Note 'Core' at (10, 20)>"
    assert repr(lan["R1"].ports).startswith("<Ports of R1: GigabitEthernet0/0")
    assert shape in lan.shapes and note in lan.notes


def test_exports_these_names():
    for name in ("End", "Interface", "Pdu", "RsaKey", "Profile", "Shape", "Note", "Ports"):
        assert name in pktlib.__all__
