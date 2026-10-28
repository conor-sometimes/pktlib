"""Reading IOS config the way Packet Tracer replays it."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

import pktlib
from pktlib._iosconfig import (
    blocks,
    interesting_config,
    interface_state,
    interfaces,
    merge_config,
    refused,
    setting_key,
)


def test_blocks_merge_a_header_seen_twice():
    lines = [
        "interface FastEthernet0/0",
        " no ip address",
        " shutdown",
        "!",
        "interface fa0/0",
        " ip address 10.0.0.1 255.0.0.0",
        " no shutdown",
    ]
    assert blocks(lines) == [
        ("interface FastEthernet0/0", ["no ip address", "shutdown", "ip address 10.0.0.1 255.0.0.0", "no shutdown"])
    ]


def test_blocks_expand_interface_range():
    out = blocks(["interface range fa0/1 - 2", " switchport mode access"])
    assert out == [
        ("interface FastEthernet0/1", ["switchport mode access"]),
        ("interface FastEthernet0/2", ["switchport mode access"]),
    ]


def test_blocks_keep_top_level_lines_once():
    assert blocks(["hostname R1", "!", "hostname R1", "ip routing"]) == [("hostname R1", []), ("ip routing", [])]


@pytest.mark.parametrize(
    "body,want",
    [
        (["no ip address", "shutdown"], (None, None, False)),
        (["ip address 1.1.1.1 255.0.0.0"], ("1.1.1.1", "255.0.0.0", True)),  # show run omits `no shutdown`
        (["ip address 1.1.1.1 255.0.0.0", "shutdown"], ("1.1.1.1", "255.0.0.0", False)),
        (["shutdown", "ip address 1.1.1.1 255.0.0.0", "no shutdown"], ("1.1.1.1", "255.0.0.0", True)),
        (["ip address 1.1.1.1 255.0.0.0", "no ip address"], (None, None, True)),  # unaddressed, not shut
        (["no shutdown"], (None, None, True)),
        ([], (None, None, True)),  # a switch port: Packet Tracer writes nothing and it's up
        (["ip address 1.1.1.1 255.0.0.0", "ip address 2.2.2.1 255.0.0.0 secondary"], ("1.1.1.1", "255.0.0.0", True)),
        (["ip address 2.2.2.1 255.0.0.0 secondary", "ip address 1.1.1.1 255.0.0.0"], ("1.1.1.1", "255.0.0.0", True)),
    ],
)
def test_interface_state(body, want):
    assert interface_state(body)[:3] == want


def test_interface_state_keeps_every_hsrp_line():
    rest = interface_state(["standby 1 ip 10.0.0.1", "standby 1 priority 110", "standby 1 preempt"])[3]
    assert rest == {
        "standby 1 ip": "standby 1 ip 10.0.0.1",
        "standby 1 priority": "standby 1 priority 110",
        "standby 1": "standby 1 preempt",
    }


@pytest.mark.parametrize(
    "line,key",
    [
        ("clock rate 64000", "clock rate"),
        ("switchport access vlan 10", "switchport access vlan"),
        ("switchport mode trunk", "switchport mode"),
        ("description to the core", "description"),
        ("no cdp enable", "cdp enable"),
        ("bandwidth 64", "bandwidth"),
        ("encapsulation dot1Q 10", "encapsulation dot1Q"),
        ("", ""),
    ],
)
def test_setting_key(line, key):
    assert setting_key(line) == key


def test_interfaces_reads_subinterfaces_and_svis():
    cfg = [
        "interface fa0/0.10",
        " encapsulation dot1Q 10",
        " ip address 10.0.10.1 255.255.255.0",
        "interface vlan 20",
        " ip address 10.0.20.1 255.255.255.0",
        " no shutdown",
    ]
    assert interfaces(cfg) == {
        "FastEthernet0/0.10": ("10.0.10.1", "255.255.255.0", True),
        "Vlan20": ("10.0.20.1", "255.255.255.0", True),
    }


def test_interesting_config_keeps_what_was_set(routed):
    """It drops structural lines (version, hostname, end) and untouched interfaces; telling
    a setting from the model's factory default is to_python's job, per model."""
    out = interesting_config(routed.device("R1").running_config)
    assert "version 12.4" not in out and "hostname R1" not in out and "end" not in out
    assert "router rip" in out and " version 2" in out
    assert "interface FastEthernet0/0" in out and " no shutdown" in out
    script = pktlib.to_python(routed)
    assert "no service timestamps" not in script  # factory default on an 1841: not exported


@given(st.lists(st.text(alphabet=" abcdefghinoprstuvw0123456789./!-", max_size=40), max_size=40))
def test_fuzz_config_readers_never_crash(lines):
    blocks(lines)
    interfaces(lines)
    interesting_config(lines)


# --- merge_config: adding commands the way IOS would save them -------------
# Found in Packet Tracer 8.2 on 25 Oct 2026: a channel-group in a second copy of
# an interface block is dropped on load, and an `interface Port-channel` after
# the member ports makes a later `router ospf` vanish.

SWITCH = [
    "hostname SW",
    "!",
    "interface FastEthernet0/1",
    "!",
    "interface FastEthernet0/2",
    "!",
    "interface Vlan1",
    " no ip address",
    " shutdown",
    "!",
    "line vty 0 4",
    " login",
    "!",
    "end",
]


def test_merge_goes_into_the_existing_block():
    out = merge_config(SWITCH, ["interface fa0/1", " channel-group 1 mode active"])
    assert out.count("interface FastEthernet0/1") == 1
    i = out.index("interface FastEthernet0/1")
    assert out[i + 1] == " channel-group 1 mode active" and out[i + 2] == "!"


def test_merge_port_channel_goes_ahead_of_the_ports():
    out = merge_config(SWITCH, ["interface port-channel 1", " switchport mode trunk"])
    assert out.index("interface Port-channel1") < out.index("interface FastEthernet0/1")
    assert out[out.index("interface Port-channel1") + 1] == " switchport mode trunk"
    # said again later, it merges like any other interface
    again = merge_config(out, ["interface po1", " description to CORE2"])
    assert again.count("interface Port-channel1") == 1 and " description to CORE2" in again


def test_merge_replaces_factory_shutdown_and_no_ip_address():
    out = merge_config(SWITCH, ["interface vlan 1", " ip address 10.0.0.1 255.0.0.0", " no shutdown"])
    i = out.index("interface Vlan1")
    assert out[i + 1 : i + 4] == [" ip address 10.0.0.1 255.0.0.0", " no shutdown", "!"]


def test_merge_keeps_secondary_addresses():
    out = merge_config(SWITCH, ["interface vlan 1", " ip address 10.0.0.1 255.0.0.0"])
    out = merge_config(out, ["interface vlan 1", " ip address 10.1.0.1 255.255.0.0 secondary"])
    assert " ip address 10.0.0.1 255.0.0.0" in out and " ip address 10.1.0.1 255.255.0.0 secondary" in out


def test_merge_line_and_router_blocks():
    out = merge_config(SWITCH, ["line vty 0 4", " password cisco"])
    assert out.count("line vty 0 4") == 1 and out[out.index("line vty 0 4") + 2] == " password cisco"
    out = merge_config(out, ["router ospf 1", " network 10.0.0.0 0.255.255.255 area 0"])
    out = merge_config(out, ["router ospf 1", " passive-interface default"])
    assert out.count("router ospf 1") == 1


def test_merge_new_blocks_and_one_liners_go_before_end():
    out = merge_config(SWITCH, ["ip routing", "interface vlan 10", " ip address 10.0.0.1 255.0.0.0"])
    assert out[-1] == "end"
    assert out.index("ip routing") < out.index("interface Vlan10") < out.index("end")
    assert out.index("interface Vlan10") > out.index("line vty 0 4")


def test_the_same_one_liner_again_is_not_repeated():
    """Entering a command that's already there changes nothing, as in IOS (and so
    config is idempotent: tests/test_properties.py). Comments stay as typed."""
    out = merge_config(["hostname A", "ip routing", "end"], ["ip routing", "!"])
    assert out.count("ip routing") == 1
    assert out[:2] == ["hostname A", "ip routing"] and out[-1] == "end"


def test_merge_leaves_input_alone():
    before = list(SWITCH)
    merge_config(SWITCH, ["interface fa0/1", " shutdown"])
    assert before == SWITCH


_IFACES = st.sampled_from(["fa0/1", "fa0/2", "vlan 1", "vlan 10", "g0/1"])
_LINES = st.sampled_from(
    [
        " shutdown",
        " no shutdown",
        " ip address 10.0.0.1 255.0.0.0",
        " no ip address",
        " description x",
        " switchport mode trunk",
        " channel-group 1 mode active",
    ]
)


@given(st.lists(st.tuples(_IFACES, st.lists(_LINES, max_size=4)), max_size=8))
def test_fuzz_merge_gives_the_same_state_as_replaying(cmds):
    """Merging is only a tidier layout: each interface ends up with the same
    address and up/down state as replaying the commands appended at the end."""
    flat = [l for name, body in cmds for l in [f"interface {name}"] + body]
    merged = merge_config(SWITCH, flat)
    appended = SWITCH[:-1] + flat + ["!", "end"]
    assert interfaces(merged) == interfaces(appended)
    assert merged.count("end") == 1 and merged[-1] == "end"
    headers = [l for l in merged if l.startswith("interface ")]
    assert len(headers) == len(set(headers))


# --- refused: config Packet Tracer 8.2 won't apply (each seen in the GUI) ---


@pytest.mark.parametrize(
    "line",
    [
        " default-information originate metric 10",
        " default-information originate metric-type 1",
        " default-information originate always metric 5",
        "interface range fa0/1 - 2",
    ],
)
def test_refused_catches_what_packet_tracer_drops(line):
    assert [l for l, _ in refused([line])] == [line]


@pytest.mark.parametrize(
    "line",
    [
        " default-information originate",
        " default-information originate always",
        "interface FastEthernet0/1",
        " metric 10",
        "router ospf 1",
    ],
)
def test_refused_leaves_good_config_alone(line):
    assert refused([line]) == []


@given(st.lists(st.text(alphabet=" abcdefghilmnoprstuvy-0123456789", max_size=50), max_size=30))
def test_fuzz_refused_never_crashes(lines):
    for line, why in refused(lines):
        assert line in lines and why


def test_repeatable_settings_are_all_kept():
    """Found by the stress tests: two helper addresses collapsed to one, and a
    secondary address was read as the primary."""
    rest = interface_state(
        [
            "ip address 10.0.0.1 255.0.0.0",
            "ip address 10.1.0.1 255.255.0.0 secondary",
            "ip helper-address 10.9.9.1",
            "ip helper-address 10.9.9.2",
        ]
    )[3]
    assert {
        "ip helper-address 10.9.9.1",
        "ip helper-address 10.9.9.2",
        "ip address 10.1.0.1 255.255.0.0 secondary",
    } <= set(rest.values())


def test_single_value_settings_replace_in_place():
    lines = ["hostname R1", "spanning-tree mode pvst", "interface Vlan1", "!", "end"]
    out = merge_config(lines, ["spanning-tree mode rapid-pvst", "hostname CORE"])
    assert out.count("spanning-tree mode rapid-pvst") == 1 and "spanning-tree mode pvst" not in out
    assert out[0] == "hostname CORE"


def test_dhcp_pools_and_acls_merge():
    lines = ["ip dhcp pool LAN", " network 10.0.0.0 255.0.0.0", "!", "end"]
    out = merge_config(
        lines, ["ip dhcp pool LAN", " default-router 10.0.0.1", "ip access-list extended IN", " permit ip any any"]
    )
    assert out.count("ip dhcp pool LAN") == 1 and " default-router 10.0.0.1" in out
    out = merge_config(out, ["ip access-list extended IN", " deny ip any host 1.1.1.1"])
    assert out.count("ip access-list extended IN") == 1


def test_ipv6_unicast_routing_goes_ahead_of_the_interfaces():
    """Packet Tracer replays the file in order; written near the end it
    refused every `ipv6 ospf` / `ipv6 eigrp` interface line (stress test
    rt05, checked in Packet Tracer 8.2 on 25 Oct)."""
    lines = ["hostname R", "!", "interface GigabitEthernet0/0", " no ip address", "!", "end"]
    out = merge_config(
        lines,
        ["ipv6 unicast-routing", "interface g0/0", " ipv6 ospf 1 area 0", "ipv6 router ospf 1", " router-id 1.1.1.1"],
    )
    assert out.index("ipv6 unicast-routing") < out.index("interface GigabitEthernet0/0")
    assert out.count("ipv6 unicast-routing") == 1
    assert merge_config(out, ["ipv6 unicast-routing"]).count("ipv6 unicast-routing") == 1


def test_one_value_settings_replace_inside_blocks():
    """A second `password` on a line replaces the first, as re-entering it in
    IOS does (found building an assignment-style lab: `password cisco` and
    `password cisco12345` both ended up under `line con 0`)."""
    lines = [
        "no service password-encryption",
        "line con 0",
        " password cisco",
        " login",
        "!",
        "interface FastEthernet0/1",
        " switchport access vlan 10",
        " switchport mode access",
        "!",
        "end",
    ]
    out = merge_config(
        lines,
        [
            "service password-encryption",
            "line con 0",
            " password cisco12345",
            " exec-timeout 15 0",
            "interface fa0/1",
            " switchport access vlan 20",
            " switchport mode trunk",
        ],
    )
    assert "no service password-encryption" not in out and out.count("service password-encryption") == 1
    i = out.index("line con 0")
    assert out[i + 1 : out.index("!", i)] == [" login", " password cisco12345", " exec-timeout 15 0"]
    j = out.index("interface FastEthernet0/1")
    assert out[j + 1 : out.index("!", j)] == [" switchport access vlan 20", " switchport mode trunk"]


def test_no_form_replaces_the_switch():
    out = merge_config(["service password-encryption", "end"], ["no service password-encryption"])
    assert out == ["no service password-encryption", "end"]


def test_zones_crypto_and_ips_go_ahead_of_the_interfaces():
    # an interface's `zone-member security X` is refused if zone X comes later
    base = ["hostname R3", "!", "interface Serial0/0/1", " ip address 10.2.2.1 255.255.255.252", "!", "end"]
    out = merge_config(
        base,
        [
            "zone security IN-ZONE",
            "crypto map VMAP 10 ipsec-isakmp",
            " set peer 10.1.1.1",
            "ip ips name IPS-RULE",
            "interface Serial0/0/1",
            " zone-member security IN-ZONE",
            "access-list 110 permit ip any any",
        ],
    )
    iface = out.index("interface Serial0/0/1")
    assert (
        out.index("zone security IN-ZONE")
        < out.index("crypto map VMAP 10 ipsec-isakmp")
        < out.index("ip ips name IPS-RULE")
        < iface
    )
    assert out[out.index("crypto map VMAP 10 ipsec-isakmp") + 1] == " set peer 10.1.1.1"
    assert out.index("access-list 110 permit ip any any") > iface


def test_port_channels_go_in_number_order():
    """Found writing the CCNA EtherChannel example: Port-channel2 went ahead of Port-channel1."""
    cmds = ["interface port-channel 1", " switchport mode trunk", "interface port-channel 2", " switchport mode trunk"]
    out = merge_config(SWITCH, cmds)
    po = [line for line in out if line.startswith("interface Port-channel")]
    assert po == ["interface Port-channel1", "interface Port-channel2"]
    assert out.index("interface Port-channel2") < next(
        i for i, line in enumerate(out) if line.startswith("interface FastEthernet")
    )


def test_refused_ipv6_routing_lines_only_in_their_block():
    """Checks 18 and 19 (26 Oct 2026): both lines were gone from Packet
    Tracer's re-save, merged block or not, and V6-B had no ::/0."""
    ospf6 = ["ipv6 router ospf 1", " default-information originate always"]
    eigrp6 = ["ipv6 router eigrp 200", " redistribute ospf 1 metric 1544 20000 255 1 1500 include-connected"]
    assert [l for l, _ in refused(ospf6 + eigrp6)] == [ospf6[1], eigrp6[1]]
    assert refused(["router ospf 1", " default-information originate always"]) == []


def test_refused_2960_port_lines_need_the_model():
    lines = ["interface FastEthernet0/1", " no switchport", " ip address 10.0.0.1 255.255.255.0"]
    assert refused(lines) == []
    assert refused(lines, "3560-24PS") == []  # a multilayer switch has routed ports
    assert [l for l, _ in refused(lines, "2960-24TT")] == lines[1:]
    assert refused(["interface Vlan1", " ip address 10.0.0.1 255.255.255.0"], "2960-24TT") == []
