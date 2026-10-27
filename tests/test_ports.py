"""Port names: shorthand, ranges, ordering."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pktlib import PktError, canonical_port
from pktlib._ports import expand_range, port_sort_key


@pytest.mark.parametrize(
    "given_,want",
    [
        ("fa0/1", "FastEthernet0/1"),
        ("Fa0/1", "FastEthernet0/1"),
        ("F0/1", "FastEthernet0/1"),
        ("FastEthernet0/1", "FastEthernet0/1"),
        ("fastethernet 0/1", "FastEthernet0/1"),
        ("  fa0/1  ", "FastEthernet0/1"),
        ("g0/0", "GigabitEthernet0/0"),
        ("gi0/0/1", "GigabitEthernet0/0/1"),
        ("gig1/0/24", "GigabitEthernet1/0/24"),
        ("GigabitEthernet0/0", "GigabitEthernet0/0"),
        ("se0/0/0", "Serial0/0/0"),
        ("s0/0/1", "Serial0/0/1"),
        ("Serial2/0", "Serial2/0"),
        ("e0", "Ethernet0"),
        ("eth0/1", "Ethernet0/1"),
        ("fa0", "FastEthernet0"),
        ("fa0/0.10", "FastEthernet0/0.10"),
        ("g0/0.100", "GigabitEthernet0/0.100"),
        ("vlan 1", "Vlan1"),
        ("Vlan10", "Vlan10"),
        ("lo0", "Loopback0"),
        ("loopback 1", "Loopback1"),
        ("port-channel 1", "Port-channel1"),
        ("Po1", "Port-channel1"),
    ],
)
def test_canonical(given_, want):
    assert canonical_port(given_) == want


@pytest.mark.parametrize(
    "bad", ["", " ", "fa", "0/1", "fa0/", "fa/1", "xyz0/1", "fa0/1/", "fa0..1", "fa0/1.x", "-", "fa-0/1"]
)
def test_not_port_names(bad):
    with pytest.raises(PktError):
        canonical_port(bad)


@pytest.mark.parametrize("bad", [None, 1, b"fa0/1", ["fa0/1"]])
def test_non_strings(bad):
    with pytest.raises(TypeError):
        canonical_port(bad)


@given(st.text(max_size=30))
def test_fuzz_canonical_only_raises_pkterror(s):
    try:
        out = canonical_port(s)
    except PktError:
        return
    assert canonical_port(out) == out  # canonical names are a fixed point


@pytest.mark.parametrize(
    "spec_,want",
    [
        ("fa0/1 - 3", ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"]),
        ("g1/0/23 - 24", ["GigabitEthernet1/0/23", "GigabitEthernet1/0/24"]),
        ("fa0/1 - 2 , fa0/5", ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/5"]),
        ("fa0/4", ["FastEthernet0/4"]),
        ("fa0/1-2", ["FastEthernet0/1", "FastEthernet0/2"]),
    ],
)
def test_expand_range(spec_, want):
    assert expand_range(spec_) == want


@pytest.mark.parametrize("bad", ["fa0/5 - 3", "fa0/1 - x", "fa0/1 - 9999", "nonsense - 2", ""])
def test_bad_ranges(bad):
    with pytest.raises(PktError):
        expand_range(bad)


def test_ios_order():
    names = [
        "Serial0/0/1",
        "FastEthernet0/1",
        "Vlan1",
        "FastEthernet0/0.10",
        "FastEthernet0/0",
        "Serial0/0/0",
        "GigabitEthernet0/1",
        "FastEthernet0/10",
        "FastEthernet0/2",
    ]
    assert sorted(names, key=port_sort_key) == [
        "FastEthernet0/0",
        "FastEthernet0/0.10",
        "FastEthernet0/1",
        "FastEthernet0/2",
        "FastEthernet0/10",
        "GigabitEthernet0/1",
        "Serial0/0/0",
        "Serial0/0/1",
        "Vlan1",
    ]


def test_sort_key_handles_odd_names():
    assert sorted(["Switch", "PC", "FastEthernet0"], key=port_sort_key)[0] == "FastEthernet0"
