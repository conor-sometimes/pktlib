"""pktlib.activity: reading and writing Packet Tracer activities (.pka).

tests/fixtures/sample.pka was made in Packet Tracer 8.2's Activity Wizard on
27 Oct 2026 from tests/fixtures/sample-answer.pkt (a 2911 and a PC): five
items ticked in the answer tree (R1's host name and G0/0 address, PC1's
address, mask and gateway), the initial network copied from the answer with
those cleared and R1 renamed Router, one line of instructions.

Writing was checked in Packet Tracer the same day: an activity built by
make_activity() from two pktlib networks opened with its instructions; with
the answer as the starting network Check Results said "You completed the
activity" with all six items Correct; from the blank start, giving PC2 its
address in the GUI took Completion to 16% (one item of six)."""

import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import pktlib
from pktlib import PktError
from pktlib.activity import Activity, activity_from_xml, diff_items, load_activity, make_activity

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = Path(__file__).parents[1] / "scripts" / "sources"
ITEMS = [
    "R1 > Host Name",
    "R1 > Ports > GigabitEthernet0/0 > IP Address",
    "PC1 > Ports > FastEthernet0 > IP Address",
    "PC1 > Ports > FastEthernet0 > Subnet Mask",
    "PC1 > Default Gateway",
    "PC2 > Ports > FastEthernet0 > IP Address",
]


@pytest.fixture(scope="module")
def act():
    return load_activity(FIXTURES / "sample.pka")


def lab(done: bool) -> pktlib.Network:
    n = pktlib.new(seed=40)
    r = n.router("R1", "2911", at=(300, 120))
    sw = n.switch("SW1", at=(300, 260))
    r["g0/0"].connect(sw["g0/1"])
    for i in (1, 2):
        pc = n.pc(f"PC{i}", at=(200 * i, 400))
        pc["fa0"].connect(sw[f"fa0/{i}"])
        if done:
            pc.set_ip(f"192.168.5.{10 + i}/24", gateway="192.168.5.1")
    if done:
        r.config("hostname GW")
        r["g0/0"].address = "192.168.5.1/24"
    return n


def test_instructions_and_items(act):
    assert act.instructions == [
        "Give R1 G0/0 the address 10.0.0.1/24 and PC1 the address 10.0.0.10/24 with gateway 10.0.0.1."
    ]
    assert [(i.path, i.expected, i.initial) for i in act.items] == [
        (("R1", "Ports", "GigabitEthernet0/0", "IP Address"), "10.0.0.1", "0.0.0.0"),
        (("R1", "Host Name"), "R1", "Router"),
        (("PC1", "Ports", "FastEthernet0", "IP Address"), "10.0.0.10", "0.0.0.0"),
        (("PC1", "Ports", "FastEthernet0", "Subnet Mask"), "255.255.255.0", "0.0.0.0"),
        (("PC1", "Default Gateway"), "10.0.0.1", "0.0.0.0"),
    ]
    assert all(i.points == 1 for i in act.items)


def test_the_networks(act):
    assert act.answer.device("R1").hostname == "R1"
    assert act.answer.device("PC1")["fa0"].address == "10.0.0.10/24"
    assert act.initial.device("R1").hostname == "Router"
    assert act.initial.device("PC1")["fa0"].address is None


def test_score(act):
    assert [ok for _, ok in act.score(act.answer)] == [True] * 5
    assert [ok for _, ok in act.score(act.initial)] == [False] * 5
    assert [ok for _, ok in act.score(pktlib.load(FIXTURES / "sample-answer.pkt"))] == [True] * 5


def test_make_activity_and_read_it_back(tmp_path):
    made = make_activity(lab(True), lab(False), ITEMS, "Address the LAN.")
    assert [(i.expected, i.initial) for i in made.items] == [
        ("GW", "R1"),
        ("192.168.5.1", "0.0.0.0"),
        ("192.168.5.11", "0.0.0.0"),
        ("255.255.255.0", "0.0.0.0"),
        ("192.168.5.1", "0.0.0.0"),
        ("192.168.5.12", "0.0.0.0"),
    ]
    made.save(tmp_path / "lab.pka")
    back = load_activity(tmp_path / "lab.pka")
    assert back.instructions == ["Address the LAN."]

    def fields(a):
        return [(i.path, i.expected, i.initial) for i in a.items]

    assert fields(back) == fields(made)
    assert [ok for _, ok in back.score(back.answer)] == [True] * 6
    assert [ok for _, ok in back.score(back.initial)] == [False] * 6


def test_written_layout_follows_the_wizard():
    """The initial network goes in the first two slots (Packet Tracer opens and
    resets to the second), the answer in the third; the first keeps the image
    banks; the trees are indented (unindented, Packet Tracer refused the file)."""
    root = ET.fromstring(make_activity(lab(True), lab(False), ITEMS[:2]).to_xml())
    first, second, third = root.findall("PACKETTRACER5")
    assert first.find("PIXMAPBANK") is not None and second.find("PIXMAPBANK") is None
    assert first.find("CEPS") is None and root.find("CEPS") is not None
    assert "hostname GW" not in ET.tostring(second, encoding="unicode")
    assert "hostname GW" in ET.tostring(third, encoding="unicode")
    tree = root.find("COMPARISONS")
    node = tree.find("NODE") if tree is not None else None
    assert node is not None and (node.text or "").strip() == ""  # whitespace inside
    assert "\n" in (node.text or "")


def test_a_loaded_activity_saves_and_reloads(act, tmp_path):
    Activity(act.initial, act.answer, act.instructions, act.items).save(tmp_path / "again.pka")
    again = load_activity(tmp_path / "again.pka")
    assert [(i.path, i.expected, i.initial) for i in again.items] == [
        (i.path, i.expected, i.initial) for i in act.items
    ]


def test_items_pktlib_cant_write_are_refused():
    with pytest.raises(pktlib.PktError, match="can't write 'R1 > MTU'"):
        make_activity(lab(True), lab(False), ["R1 > MTU"])
    with pytest.raises(pktlib.PktError, match="no such device or port"):
        make_activity(lab(True), lab(False), ["PC9 > Default Gateway"])


def test_a_pkt_is_not_an_activity():
    with pytest.raises(pktlib.FileFormatError, match="not an activity"):
        activity_from_xml(pktlib.decode((FIXTURES / "sample-answer.pkt").read_bytes()))


def test_load_points_a_pka_at_load_activity():
    with pytest.raises(pktlib.FileFormatError, match="load_activity"):
        pktlib.load(FIXTURES / "sample.pka")


# --- the richer kinds: VLANs, switch ports, OSPF, config lines, connectivity tests ---
#
# tests/fixtures/rich.pka was made in the Activity Wizard on 27 Oct 2026 from
# rich-answer.pkt and rich-start.pkt (pktlib-built: R1 router-on-a-stick for VLANs
# 10 SALES and 20 ENG on SW1, OSPF to R2, a server behind R2; the start has the
# addresses but no VLANs, OSPF or enable secret). Ticked: config lines, OSPF
# networks and router ID, Fa0/1's access VLAN and mode, both VLAN names; two
# connectivity tests (PC1 and PC2 to SERVER, the second set to Fail). An activity
# make_activity() built from the same networks with the items below opened in
# Packet Tracer: from the answer, every item and all three tests Correct and "You
# completed the activity" (once OSPF had converged); from the start, every item
# Incorrect but R1's host name and SW1's trunk Port Mode, as score() says.

RICH_ITEMS = [
    "R1 > Host Name",
    "SW1 > VLANS > VLAN 10 > VLAN Name",
    "SW1 > VLANS > VLAN 20 > VLAN Name",
    "SW1 > Ports > FastEthernet0/1 > Access VLAN",
    "SW1 > Ports > FastEthernet0/2 > Access VLAN",
    "SW1 > Ports > GigabitEthernet0/1 > Port Mode",
    "R1 > OSPF > Process ID 1 > Router ID",
    "R1 > OSPF > Process ID 1 > Networks > Route2",
    "R2 > OSPF > Process ID 1 > Networks > Route0",
    ("R1", "Running Configuration", "enable secret class12345"),
    ("R2", "Running Configuration", "router ospf 1", "network 172.16.1.0 0.0.0.255 area 0"),
]


@pytest.fixture(scope="module")
def rich():
    return load_activity(FIXTURES / "rich.pka")


def test_rich_items_as_the_wizard_wrote_them(rich):
    def key(i):  # a config line by its ID, anything else by its path below the device
        return i.node_id if "LINES" in i.path else " > ".join(i.path[1:])

    got = {key(i): i.expected for i in rich.items}
    assert got["VLANS > VLAN 10 > VLAN Name"] == "SALES"
    assert got["Ports > FastEthernet0/1 > Access VLAN"] == "10"
    assert got["Ports > FastEthernet0/1 > Port Mode"] == "1"
    assert got["router ospf 1 network 192.168.10.0 0.0.0.255 area 0"] == " network 192.168.10.0 0.0.0.255 area 0"
    assert got["enable secret 5 $1$mERr$8BPXRaZKXzJUe84Ckfffz."] == "enable secret 5 $1$mERr$8BPXRaZKXzJUe84Ckfffz."
    ospf = {i.path[-1]: i.expected for i in rich.items if "OSPF" in i.path}
    assert ospf == {
        "Router ID": "192.168.20.1",
        "Route0": "192.168.10.0 0.0.0.255 0",
        "Route1": "192.168.20.0 0.0.0.255 0",
        "Route2": "10.0.12.0 0.0.0.3 0",
    }
    assert rich.tests == [("PC1", "SERVER", True), ("PC2", "SERVER", False)]


def test_rich_scores(rich):
    assert all(ok for _, ok in rich.score(rich.answer))
    # a pktlib-written answer reads the same, the secret included (Packet Tracer
    # shows `enable secret class12345` as type 5 with the salt mERr)
    assert all(ok for _, ok in rich.score(pktlib.load(FIXTURES / "rich-answer.pkt")))
    start = {" > ".join(i.path): ok for i, ok in rich.score(pktlib.load(FIXTURES / "rich-start.pkt"))}
    assert [p for p, ok in start.items() if ok] == ["SW1 > Ports > FastEthernet0/1 > Port Mode"]  # unset reads as 1


def test_make_a_rich_activity(tmp_path):
    answer, start = pktlib.load(FIXTURES / "rich-answer.pkt"), pktlib.load(FIXTURES / "rich-start.pkt")
    made = make_activity(
        answer, start, RICH_ITEMS, "Do it all.", tests=[("PC1", "SERVER"), ("PC2", "SERVER"), ("PC1", "PC2", True)]
    )
    made.save(tmp_path / "rich.pka")
    back = load_activity(tmp_path / "rich.pka")
    assert back.tests == [("PC1", "SERVER", True), ("PC2", "SERVER", True), ("PC1", "PC2", True)]
    assert all(ok for _, ok in back.score(back.answer))
    by_kind = {i.path[-1] if "LINES" not in i.path else i.node_id: (i.expected, i.initial) for i in back.items}
    assert by_kind["Port Mode"] == ("0", "0")  # the trunk is in both
    assert by_kind["enable secret 5 $1$mERr$8BPXRaZKXzJUe84Ckfffz."][1] == ""
    assert by_kind["router ospf 1 network 172.16.1.0 0.0.0.255 area 0"] == (" network 172.16.1.0 0.0.0.255 area 0", "")
    assert len(pktlib.load(FIXTURES / "rich-answer.pkt").pdus) == 0  # the tests went on a copy


def test_config_line_ids_are_the_bare_line():
    """Packet Tracer finds a config item by its ID; with the line number in the ID
    (pktlib's first try) the item vanished from Check Results."""
    answer, start = pktlib.load(FIXTURES / "rich-answer.pkt"), pktlib.load(FIXTURES / "rich-start.pkt")
    made = make_activity(answer, start, RICH_ITEMS[-2:])
    assert [i.node_id for i in made.items] == [
        "enable secret 5 $1$mERr$8BPXRaZKXzJUe84Ckfffz.",
        "router ospf 1 network 172.16.1.0 0.0.0.255 area 0",
    ]
    with pytest.raises(pktlib.PktError, match="isn't in R1's config"):
        make_activity(answer, start, [("R1", "Running Configuration", "no such line")])


def test_diff_items_finds_what_changed():
    from pktlib.activity import diff_items

    got = diff_items(pktlib.load(FIXTURES / "rich-answer.pkt"), pktlib.load(FIXTURES / "rich-start.pkt"))
    assert ("SW1", "Ports", "FastEthernet0/1", "Access VLAN") in got
    assert ("SW1", "VLANS", "VLAN 20", "VLAN Name") in got
    assert ("R2", "OSPF", "Process ID 1", "Networks", "Route1") in got
    assert ("R1", "Running Configuration", "enable secret class12345") in got
    # graded by other kinds, or noise: no interface, router ospf, licence or "!" lines
    lines = [p for p in got if p[1] == "Running Configuration"]
    assert lines == [
        ("R1", "Running Configuration", "enable secret class12345"),
        ("R2", "Running Configuration", "enable secret class12345"),
    ]
    assert diff_items(pktlib.load(FIXTURES / "rich-answer.pkt"), pktlib.load(FIXTURES / "rich-answer.pkt")) == []


def test_tests_reuse_the_labs_pings_and_go_first(tmp_path):
    """Check Results listed only the tests ahead of the first untested ping (27 Oct
    2026), so a ping the answer already has is reused, and tested ones go first."""
    answer, start = pktlib.load(FIXTURES / "rich-answer.pkt"), pktlib.load(FIXTURES / "rich-start.pkt")
    answer.ping("PC2", "SERVER")
    answer.ping("PC1", "PC2")
    act = make_activity(answer, start, ["R1 > Host Name"], tests=[("PC1", "PC2"), ("PC1", "SERVER")])
    act.save(tmp_path / "t.pka")
    back = load_activity(tmp_path / "t.pka")
    assert back.tests == [("PC1", "PC2", True), ("PC1", "SERVER", True)]
    pairs = [(p.source, p.destination) for p in back.answer.pdus]
    assert pairs == [("PC1", "PC2"), ("PC1", "SERVER"), ("PC2", "SERVER")]


def test_bad_item_paths_are_refused():
    answer, start = lab(True), lab(False)
    for item, why in [
        ("R1 > Running Configuration > a > b > c", "give a config line"),
        ("R9 > Running Configuration > hostname GW", "no device 'R9'"),
        ("PC1 > Ports > FastEthernet9 > IP Address", "no such device or port"),
        ("R1 > Ports > GigabitEthernet0/9 > IP Address", "no such device or port"),
        ("R1", "can't write"),
    ]:
        with pytest.raises(pktlib.PktError, match=why):
            make_activity(answer, start, [item]).to_xml()


def test_an_item_prints_as_its_path():
    made = make_activity(lab(True), lab(False), ["R1 > Host Name"])
    assert str(made.items[0]) == "R1 > Host Name = GW"


def test_an_activity_holds_three_networks():
    xml = pktlib.decode((FIXTURES / "sample.pka").read_bytes())
    root = ET.fromstring(xml)
    root.remove(root.findall("PACKETTRACER5")[0])
    with pytest.raises(pktlib.FileFormatError, match="has 2"):
        activity_from_xml(ET.tostring(root))


@pytest.mark.parametrize(
    ("loopback", "want"), [("10.9.9.9/32", "10.9.9.9"), (None, "192.168.5.1")], ids=["loopback", "up-port"]
)
def test_router_id_without_a_router_id_line(loopback, want):
    """With no `router-id`, the item's value is the highest loopback address, else the
    highest address on an up interface (the rule activity.py reads it by)."""
    answer = lab(True)
    r = answer.device("R1")
    r.config(["router ospf 1", " network 192.168.5.0 0.0.0.255 area 0"])
    if loopback:
        r.config(["interface Loopback0", f" ip address {loopback.split('/')[0]} 255.255.255.255"])
    made = make_activity(answer, lab(False), ["R1 > OSPF > Process ID 1 > Router ID"])
    assert made.items[0].expected == want


# --- ACLs, NAT and DHCP: tests/fixtures/rich2.pka ----------------------------
# Made in Packet Tracer 8.2's Activity Wizard on 27 Oct 2026 from rich2-answer.pkt and
# rich2-start.pkt (scripts/sources/rich2.py, saved by Packet Tracer). Graded as a
# student from the start, each of its 11 items turned Correct on its own as its config
# went in, and the activity completed; ACL line order counted, `overload` didn't.

RICH2 = [
    ("R1 > Ports > GigabitEthernet0/0 > Access-group In", "110"),
    ("R1 > Ports > GigabitEthernet0/0 > Access-group Out", "20"),
    ("R1 > Ports > GigabitEthernet0/0 > NAT Mode", "1"),
    ("R1 > ACL > 20", "deny host 9.9.9.9\npermit any"),
    ("R1 > ACL > 110", "deny icmp 192.168.1.0 0.0.0.255 host 8.8.4.4\npermit ip any any"),
    ("R1 > NAT > Inside Source List > NAT Source Setting 1", "GigabitEthernet0/1"),
    ("R1 > NAT > Inside Source Static > NAT Source Setting 1", "192.168.1.10 203.0.113.10 "),
    ("R1 > DHCP Server > Pools > Pool LAN > DNS server IP", "8.8.8.8"),
    ("R1 > DHCP Server > Pools > Pool LAN > Default Gateway", "192.168.1.1"),
    ("R1 > DHCP Server > Pools > Pool LAN > Network Address", "192.168.1.0"),
    ("R1 > DHCP Server > Excluded Addresses > 192.168.1.1 192.168.1.20", "192.168.1.1 192.168.1.20"),
]


@pytest.fixture(scope="module")
def rich2():
    return load_activity(FIXTURES / "rich2.pka")


def _tree(xml: bytes) -> dict[tuple[str, ...], tuple[str | None, str | None, str | None]]:
    """Every ticked node of COMPARISONS: path -> (ID, eclass, value)."""
    out = {}

    def walk(node, path):
        name = node.find("NAME")
        here = (*path, name.text)
        if name.get("checkType") in ("1", "2"):
            out[here] = (node.findtext("ID"), name.get("eclass"), name.get("nodeValue"))
        for child in node.findall("NODE"):
            walk(child, here)

    tree = ET.fromstring(xml).find("COMPARISONS")
    assert tree is not None
    for top in tree.findall("NODE"):
        walk(top, ())
    return out


def test_rich2_items_and_scores(rich2):
    assert [(" > ".join(i.path), i.expected) for i in rich2.items] == RICH2
    answer = pktlib.load(FIXTURES / "rich2-answer.pkt")
    start = pktlib.load(FIXTURES / "rich2-start.pkt")
    assert all(ok for _, ok in rich2.score(answer))
    assert not any(ok for _, ok in rich2.score(start))
    # the wizard leaves what the start lacks out of INITIALSETUP; read from the start instead
    assert {" > ".join(i.path): i.initial for i in rich2.items}["R1 > Ports > GigabitEthernet0/0 > NAT Mode"] == "0"


@pytest.mark.parametrize("source", ["saved", "built"])
def test_rich2_written_as_the_wizard_wrote_it(rich2, source):
    """The same items made by make_activity give the wizard's tree: values, IDs and
    classes, from the networks Packet Tracer saved and from rich2.py's own build. Only
    Routes > Static Routes differs: the wizard ticks it, but it grades nothing."""
    if source == "saved":
        answer, start = pktlib.load(FIXTURES / "rich2-answer.pkt"), pktlib.load(FIXTURES / "rich2-start.pkt")
    else:
        built = runpy.run_path(str(SOURCES / "rich2.py"), run_name="rich2")
        answer, start = built["build"](True), built["build"](False)
    ours = _tree(make_activity(answer, start, [p for p, _ in RICH2]).to_xml())
    wizard = {k: v for k, v in _tree(pktlib.decode((FIXTURES / "rich2.pka").read_bytes())).items() if "Routes" not in k}
    assert ours == wizard


def test_diff_items_grades_acls_nat_and_dhcp_once():
    built = runpy.run_path(str(SOURCES / "rich2.py"), run_name="rich2")
    answer, start = built["build"](True), built["build"](False)
    items = [" > ".join(p) for p in diff_items(answer, start)]
    assert {p for p, _ in RICH2} - set(items) == {"R1 > NAT > Inside Source List > NAT Source Setting 1"}
    lines = [p for p in items if "Running Configuration" in p]
    # what the wizard can't grade stays a config line: static routes, and PAT with its overload
    assert lines == [
        "R1 > Running Configuration > ip route 0.0.0.0 0.0.0.0 198.51.100.1",
        "R1 > Running Configuration > ip route 10.20.0.0 255.255.0.0 198.51.100.1",
        "R1 > Running Configuration > ip nat inside source list 1 interface GigabitEthernet0/1 overload",
    ]
    act = activity_from_xml(make_activity(answer, start, items).to_xml())
    assert all(ok for _, ok in act.score(answer)) and not any(ok for _, ok in act.score(start))


def test_static_routes_and_missing_nat_rules_are_refused():
    answer = pktlib.load(FIXTURES / "rich2-answer.pkt")
    with pytest.raises(PktError, match="can't grade static routes"):
        make_activity(answer, answer, ["R1 > Routes > Static Routes"])
    with pytest.raises(PktError, match="has 1 such NAT rules"):
        make_activity(answer, answer, ["R1 > NAT > Inside Source Static > NAT Source Setting 2"])


def test_a_named_acl_reads_like_a_numbered_one():
    """Packet Tracer graded `ip access-list standard 20` the same as `access-list 20`."""
    net = pktlib.new(seed=3)
    r = net.router("R1", "2911")
    r.config("ip access-list standard 20\n deny host 9.9.9.9\n permit any")
    act = make_activity(net, net, ["R1 > ACL > 20"])
    assert act.items[0].expected == "deny host 9.9.9.9\npermit any"
