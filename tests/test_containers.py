"""Networks, devices and ports behave like the Python containers they look like."""

import pytest

import pktlib
from pktlib import NotFound


@pytest.fixture
def lan(net):
    r = net.router("R1", "2911", at=(100, 100))
    sw = net.switch("S1", at=(100, 200))
    pc = net.pc("PC1", at=(100, 300))
    pc["fa0"].connect(sw["fa0/1"])
    sw["g0/1"].connect(r["g0/0"])
    return net


# --- identity -----------------------------------------------------------------


def test_the_same_thing_twice_is_equal(lan):
    assert lan.device("R1") == lan.device("R1") == lan["R1"]
    assert lan["R1"]["g0/0"] == lan["R1"]["GigabitEthernet0/0"]
    assert lan.link_at("R1", "g0/0") == lan["R1"]["g0/0"].link
    assert lan["R1"] != lan["S1"] and lan["R1"]["g0/0"] != lan["R1"]["g0/1"]


def test_usable_in_sets_and_as_keys(lan):
    assert len({lan["R1"], lan.device("R1"), lan["S1"]}) == 2
    seen = {lan["PC1"]["fa0"]: "cabled"}
    assert seen[lan["PC1"]["FastEthernet0"]] == "cabled"


def test_a_device_from_another_network_is_not_equal(lan):
    other = pktlib.new(seed=1)
    other.router("R1", "2911")
    assert other["R1"] != lan["R1"]
    assert other["R1"] not in lan


# --- Network ------------------------------------------------------------------


def test_network_is_a_collection_of_devices(lan):
    assert [d.name for d in lan] == ["R1", "S1", "PC1"]
    assert len(lan) == 3
    assert "R1" in lan and lan["R1"] in lan and "R9" not in lan and 5 not in lan
    assert repr(lan) == "<Network 8.2: 3 devices, 2 links>"


def test_missing_device(lan):
    with pytest.raises(NotFound, match="no device called 'R9'"):
        lan["R9"]


def test_a_removed_device_is_no_longer_in(lan):
    r = lan["R1"]
    lan.remove_device(r)
    assert r not in lan and "R1" not in lan
    with pytest.raises(NotFound, match="isn't in this network"):
        lan.device(r)


@pytest.mark.parametrize("by", ["name", "object"])
def test_device_or_name_everywhere(lan, by):
    def d(name):
        return name if by == "name" else lan[name]

    assert lan.link_at(d("R1"), "g0/0") is not None
    lan.disconnect(d("R1"), "g0/0")
    lan.connect(d("R1"), "g0/0", d("S1"), "g0/1")
    lan.ping(d("PC1"), d("R1"), ip="10.0.0.1")
    lan.around(d("R1"), d("S1"))
    lan.remove_device(d("PC1"))
    assert [x.name for x in lan] == ["R1", "S1"]


# --- Device -------------------------------------------------------------------


def test_device_is_a_collection_of_ports(lan):
    pc = lan["PC1"]
    assert [p.name for p in pc] == ["FastEthernet0", "Bluetooth"]
    assert len(pc) == 2
    assert "fa0" in pc and "FastEthernet0" in pc and pc["fa0"] in pc
    assert "fa0/9" not in pc and "nonsense!" not in pc and 0 not in pc
    assert lan["R1"]["g0/0"] not in pc


def test_ports_is_a_read_only_mapping_that_takes_shorthand(lan):
    ports = lan["R1"].ports
    assert ports["g0/0"] is not None and ports["g0/0"] == ports["GigabitEthernet0/0"]
    assert "g0/0" in ports and ports.get("g9/9") is None
    with pytest.raises(TypeError):
        ports["x"] = None  # type: ignore[index]
    with pytest.raises(NotFound):
        ports["g9/9"]


def test_vlans_and_licenses_are_read_only(lan):
    with pytest.raises(TypeError):
        lan["S1"].vlans[99] = "X"  # type: ignore[index]
    with pytest.raises(TypeError):
        lan["R1"].licenses["securityk9"] = "Active"  # type: ignore[index]


def test_a_device_with_no_ports_is_still_a_device(net):
    """Router-PT-Empty has no ports until a card goes in. With __len__ alone it was
    falsy, and a ping check aimed at it listed its device as '?'."""
    empty = net.add_device("BARE", "Router-PT-Empty")
    pc = net.pc("PC1", ip="10.0.0.5/24")
    assert len(empty) == 0 and empty
    assert pktlib.new(seed=1)
    net.ping(pc, empty, ip="10.0.0.1")
    assert net.pdus[0].destination == "BARE"
