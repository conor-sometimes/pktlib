"""One way to write an address everywhere, settable end-device fields, and
keyword-only options."""

import ipaddress

import pytest

import pktlib
from pktlib import PktError, Profile


@pytest.mark.parametrize("addr", ["10.0.0.5/24", "10.0.0.5 255.255.255.0", ipaddress.IPv4Interface("10.0.0.5/24")])
def test_every_form_of_address_works_everywhere(net, addr):
    pc = net.pc("PC1", ip=addr, gateway="10.0.0.1")
    assert pc["fa0"].address == "10.0.0.5/24" and pc.gateway == "10.0.0.1"
    pc2 = net.pc("PC2")
    pc2.set_ip(addr)
    assert pc2["fa0"].address == "10.0.0.5/24"
    r = net.router("R1", "2911")
    r["g0/0"].address = addr
    assert r["g0/0"].address == "10.0.0.5/24"


def test_a_pc_address_outside_its_gateway_says_how_to_move_both(net):
    pc = net.pc("PC1", ip="10.0.0.5/24", gateway="10.0.0.1")
    with pytest.raises(PktError, match=r"set both with PC1\.set_ip\('10\.1\.0\.5/24', gateway=\.\.\.\)"):
        pc["fa0"].address = "10.1.0.5/24"


def test_gateway_is_settable_and_checked(net):
    pc = net.pc("PC1", ip="10.0.0.5/24")
    pc.gateway = "10.0.0.254"
    assert pc.gateway == "10.0.0.254" and pc["fa0"].el.findtext("PORT_GATEWAY") == "10.0.0.254"
    with pytest.raises(PktError, match=r"outside 10\.0\.0\.0/24"):
        pc.gateway = "10.9.9.9"
    with pytest.raises(PktError, match="runs IOS"):
        net.router("R1", "2911").gateway = "10.0.0.1"


def test_dhcp_is_settable(net):
    pc = net.pc("PC1", ip="10.0.0.5/24")
    pc.dhcp = True
    assert pc.dhcp and pc["fa0"].address is None
    pc.dhcp = False
    assert not pc.dhcp
    with pytest.raises(TypeError):
        pc.dhcp = "yes"  # type: ignore[assignment]


def test_profile_is_settable(net):
    net.profile = "A Student"
    assert net.profile == Profile("A Student", "", "")
    net.profile = Profile("A Student", email="a@example.com")
    assert net.profile.email == "a@example.com"
    net.profile = ("B", "b@example.com", "Lab 3")
    assert net.profile == ("B", "b@example.com", "Lab 3")


def test_devices_without_a_position_never_overlap(net):
    spots = [net.pc(f"P{i}").xy for i in range(10)]
    assert len(set(spots)) == 10


def test_config_takes_a_list_and_chains(net):
    r = net.router("R1", "2911")
    assert r.config(["hostname EDGE"]).config("ip domain-name lab.local") is r
    assert "hostname EDGE" in r.running_config
    assert not hasattr(r, "configure")


@pytest.mark.parametrize(
    "call",
    [
        lambda n: n.pc("P", (0, 0)),
        lambda n: n.router("R", "2911", (0, 0)),
        lambda n: n.phone("P", (0, 0), True),
        lambda n: pktlib.new(5),  # ty: ignore[too-many-positional-arguments]
        lambda n: pktlib.models(False),  # ty: ignore[too-many-positional-arguments]
        lambda n: pktlib.decode(b"", False),  # ty: ignore[too-many-positional-arguments]
    ],
)
def test_options_are_keyword_only(net, call):
    with pytest.raises(TypeError):
        call(net)
