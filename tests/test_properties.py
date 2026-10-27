"""Properties that hold for every network and every input, checked on random ones.

`networks()` builds a random network through the public API: devices of many kinds,
cables between free ports, addresses, IOS config, VLANs, drawings, ping checks. The tests
then check what must hold for any of them.
"""

from __future__ import annotations

import contextlib
import ipaddress
import itertools
import warnings

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import PktError, PktWarning
from pktlib._iosconfig import blocks, merge_config
from pktlib._model import _interface, _prepare_commands
from pktlib._xml import fmt_num
from tests.conftest import examples

SLOW = settings(max_examples=examples(20), deadline=None, suppress_health_check=[HealthCheck.too_slow])
MODELS = ["2911", "1841+WIC-2T", "ISR4331", "2960-24TT", "3560-24PS", "PC-PT", "Laptop-PT", "Server-PT", "7960"]
CONFIG_LINES = st.sampled_from(
    [
        "hostname X1",
        "ip domain-name lab.local",
        "router ospf 1\n network 10.0.0.0 0.255.255.255 area 0",
        "router rip\n version 2\n network 10.0.0.0",
        "ip route 0.0.0.0 0.0.0.0 10.0.0.254",
        "interface g0/1\n description uplink",
        "interface fa0/1\n switchport mode access\n switchport access vlan 10",
        "vlan 20\n name TWENTY",
        "banner motd #lab#",
        "line vty 0 4\n password cisco\n login",
        "enable secret class",
        "interface g0/0\n shutdown",
        "interface g0/0\n no shutdown",
    ]
)


@st.composite
def networks(draw: st.DrawFn) -> pktlib.Network:
    net = pktlib.new(seed=draw(st.integers(0, 2**20)))
    models = draw(st.lists(st.sampled_from(MODELS), min_size=1, max_size=6))
    devs = [net.add_device(f"D{i}", m, at=(100 + 120 * i, 100 + 40 * (i % 3))) for i, m in enumerate(models)]
    for a, b in itertools.combinations(devs, 2):
        if not draw(st.booleans()):
            continue
        free_a = [p for p in a if p.link is None and p.type != "eBluetooth"]
        free_b = [p for p in b if p.link is None and p.type != "eBluetooth"]
        pairs = [(x, y) for x in free_a for y in free_b if x.name.startswith("Serial") == y.name.startswith("Serial")]
        if pairs:
            x, y = draw(st.sampled_from(pairs))
            x.connect(y)
    for i, d in enumerate(devs):
        if d.has_ios and d.kind == "Router" and draw(st.booleans()):
            port = draw(st.sampled_from([p for p in d if p.type != "eBluetooth"]))
            port.address = f"10.{i}.0.1/24"
        elif d.kind in ("Pc", "Laptop", "Server") and draw(st.booleans()):
            d.set_ip(f"10.{i}.0.5/24", f"10.{i}.0.1")
        if d.has_ios and d.kind not in ("IpPhone",):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", PktWarning)
                for text in draw(st.lists(CONFIG_LINES, max_size=3)):
                    with contextlib.suppress(PktError):  # a port this kind of device lacks (a switch has no g0/1)
                        d.config(text)
    if len(devs) >= 2 and draw(st.booleans()):
        net.ping(devs[0], devs[1], ip="10.0.0.1")
    if draw(st.booleans()):
        net.around(*devs, label=draw(st.sampled_from([None, "LAB"])))
    return net


# --- whole networks ---------------------------------------------------------------------


@SLOW
@given(networks())
def test_save_and_load_keep_every_byte(net):
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.to_xml() == net.to_xml()


@SLOW
@given(networks())
def test_the_audit_says_the_same_after_a_reload(net):
    assert pktlib.audit(pktlib.Network.from_bytes(net.to_bytes())) == pktlib.audit(net)


@SLOW
@given(networks(), st.data())
def test_to_python_rebuilds_the_network(net, data):
    """The exported script, run, exports the same script again: nothing it can see is lost."""
    script = pktlib.to_python(net)
    scope: dict = {}
    exec(compile(script.replace("net.save('out.pkt')", ""), "<export>", "exec"), scope)
    rebuilt = scope["net"]
    assert pktlib.to_python(rebuilt) == script
    assert {(*link.ends, link.cable) for link in rebuilt.links} == {(*link.ends, link.cable) for link in net.links}
    for d in net:
        r = rebuilt[d.name]
        assert (r.model, r.xy) == (d.model, d.xy)
        assert {p.name: p.address for p in r} == {p.name: p.address for p in d}


@SLOW
@given(st.integers(0, 2**20), st.lists(st.sampled_from(MODELS), min_size=1, max_size=4))
def test_the_same_seed_writes_the_same_bytes(seed, models):
    def build() -> bytes:
        net = pktlib.new(seed=seed)
        for i, m in enumerate(models):
            net.add_device(f"D{i}", m)
        net.note("lab", at=(10, 10))
        return net.to_bytes()

    assert build() == build()


@SLOW
@given(networks())
def test_every_cable_is_seen_from_both_ends(net):
    for link in net.links:
        a, b = link.ports
        assert a.link == link == b.link
        assert a.peer == b and b.peer == a
        assert b.device in a.device.neighbors and a.device in b.device.neighbors


# --- config -----------------------------------------------------------------------------

IOS_WORDS = st.sampled_from(
    [
        "interface",
        "g0/0",
        "fa0/1",
        "ip",
        "address",
        "10.0.0.1",
        "255.255.255.0",
        "/24",
        "no",
        "shutdown",
        "router",
        "ospf",
        "1",
        "network",
        "area",
        "0",
        "vlan",
        "10",
        "name",
        "switchport",
        "access",
        "mode",
        "trunk",
        "exit",
        "end",
        "conf",
        "t",
        "range",
        "-",
        "2",
        "description",
        "banner",
        "motd",
        "#",
        "!",
        "hostname",
        "line",
        "vty",
        "4",
    ]
)
IOS_LINES = st.builds(
    lambda indent, words: indent + " ".join(words),
    st.sampled_from(["", "", " ", "  ", "\t"]),
    st.lists(IOS_WORDS, min_size=1, max_size=6),
)


@settings(max_examples=examples(50), deadline=None)  # builds a device per example: the soak runs more
@given(st.sampled_from(["2911", "2960-24TT", "3560-24PS"]), st.lists(IOS_LINES, max_size=12))
def test_config_takes_any_ios_like_text_or_refuses_it_cleanly(model, lines):
    net = pktlib.new(seed=1)
    d = net.add_device("D", model)
    before = net.to_xml()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PktWarning)
        try:
            d.config(lines)
        except PktError:
            assert net.to_xml() == before
            return
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.to_xml() == net.to_xml()
    assert not any(line.strip() in ("exit", "end") for line in d.running_config[:-1])


MERGEABLE_CONFIG = st.lists(
    st.sampled_from(
        [
            "hostname R9",
            "ip routing",
            "no ip domain-lookup",
            "ip route 0.0.0.0 0.0.0.0 10.0.0.254",
            "interface g0/1\n ip address 10.1.0.1 255.255.255.0\n no shutdown",
            "interface g0/1\n description to core",
            "interface g0/0\n shutdown",
            "router ospf 1\n network 10.0.0.0 0.255.255.255 area 0",
            "router ospf 1\n passive-interface g0/0",
            "line vty 0 4\n password cisco\n login",
            "ip dhcp pool LAN\n default-router 10.0.0.1",
            "banner motd #hi#",
        ]
    ),
    max_size=8,
).map(lambda chunks: [line for chunk in chunks for line in chunk.split("\n")])


@settings(max_examples=examples(200), deadline=None)
@given(MERGEABLE_CONFIG)
def test_entering_the_same_config_twice_changes_nothing_more(lines):
    """For one-line commands and the blocks pktlib merges (interface, router, line, dhcp
    pool, ...). Other blocks entered twice get a second copy: see TODO.md."""
    try:
        cmds = _prepare_commands(lines)
    except PktError:
        assume(False)
    base = pktlib.new(seed=1).router("R", "2911").running_config
    once = merge_config(base, cmds)
    assert merge_config(once, cmds) == once


@settings(max_examples=examples(200))
@given(st.lists(IOS_LINES, max_size=10))
def test_prepared_commands_are_already_prepared(lines):
    try:
        once = _prepare_commands(lines)
    except PktError:
        return
    assert _prepare_commands(once) == once
    assert all("\t" not in c and c.strip() not in ("exit", "end") for c in once)


@settings(max_examples=examples(200))
@given(st.lists(IOS_LINES, max_size=10))
def test_blocks_never_lose_a_header(lines):
    cmds = [c for c in lines if c.strip()]
    headers = {" ".join(c.lower().split()) for c in cmds if not c.startswith((" ", "\t")) and c.strip() != "!"}
    seen = {" ".join(h.lower().split()) for h, _ in blocks(cmds)}
    for h in headers:
        if not h.startswith(("interface ",)):  # interfaces are renamed to their canonical form
            assert h in seen


# --- small pieces -----------------------------------------------------------------------


@given(st.ip_addresses(v=4), st.integers(0, 32))
def test_every_way_of_writing_an_address_means_the_same(ip, prefix):
    iface = ipaddress.IPv4Interface(f"{ip}/{prefix}")
    assert _interface(f"{ip}/{prefix}") == iface
    assert _interface(f"{ip} {iface.netmask}") == iface
    assert _interface(iface) == iface


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12))
def test_coordinates_never_get_an_exponent_and_read_back_close(v):
    s = fmt_num(v)
    assert "e" not in s.lower()
    assert float(s) == pytest.approx(v, rel=1e-5, abs=1e-6)
