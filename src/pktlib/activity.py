"""Packet Tracer activities (.pka): read one, score a network against it, or
write a new one from two pktlib networks.

    from pktlib.activity import load_activity, make_activity

    act = load_activity("lab.pka")
    act.instructions            # the instruction pages
    act.initial, act.answer     # Networks: what the student starts with, the answer
    for item in act.items:      # what the Activity Wizard was told to assess
        print(item)             # R1 > Ports > GigabitEthernet0/0 > IP Address = 10.0.0.1
    act.tests                   # connectivity tests: (source, destination, should succeed)
    for item, ok in act.score(pktlib.load("handed_in.pkt")):
        print(ok, item)

    act = make_activity(answer, start, [
            "R1 > Host Name",
            "PC1 > Ports > FastEthernet0 > IP Address",
            "SW1 > VLANS > VLAN 10 > VLAN Name",
            "SW1 > Ports > FastEthernet0/1 > Access VLAN",
            "R1 > OSPF > Process ID 1 > Networks > Route0",
            "R1 > ACL > 110",
            "R1 > DHCP Server > Pools > Pool LAN > Default Gateway",
            ("R1", "Running Configuration", "router ospf 1", "network 10.0.12.0 0.0.0.3 area 0"),
        ], instructions="...", tests=[("PC1", "SERVER", True)])
    act.save("lab.pka")         # opens in Packet Tracer, Check Results grades it

The item kinds, as the Activity Wizard names them (device first):
  Host Name; Default Gateway (end devices)
  Ports > <port> > IP Address | Subnet Mask | Access VLAN | Port Mode
  VLANS > VLAN <n> > VLAN Name
  OSPF > Process ID <n> > Router ID | Networks > Route<k>  (the k-th network statement)
  Ports > <port> > Access-group In | Access-group Out | NAT Mode
  ACL > <number or name>  (every line of the list, in order)
  NAT > Inside Source List | Inside Source Static > NAT Source Setting <k>  (the k-th rule)
  DHCP Server > Pools > Pool <name> > Network Address | Default Gateway | DNS server IP
  DHCP Server > Excluded Addresses > <first> <last>
  Running Configuration > <line>, or > <block header> > <line inside it>

Packet Tracer 8.2's wizard can't grade static routes (Routes > Static Routes
has no items under it), PAT's `overload`, or whether the access list a NAT rule
or access-group names exists: grade those with Running Configuration lines.

Learnt from activities made in Packet Tracer 8.2's Activity Wizard (27 Oct
2026; tests/fixtures/sample.pka and rich.pka are the originals) and from
edited copies opened there. A .pka is encrypted like a .pkt. Its XML root
<PACKETTRACER5_ACTIVITY> holds three <PACKETTRACER5> networks: Packet Tracer
opens, and resets to, the second; the third is the answer; the wizard writes
the initial network into the first two. COMPARISONS is the assessment tree
with the answer's values (a ticked item has checkType="2"); INITIALSETUP is
the same tree with the starting values (the wizard doesn't always tick it).
Packet Tracer grades from a tree holding only the ticked items and their
headings, but refuses one written without whitespace between its elements.
Connectivity tests are the answer network's first-scenario Simple PDUs with
TEST_CONDITION 3 (should succeed) or 2 (should fail).
"""

from __future__ import annotations

import copy
import gzip
import ipaddress
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import NamedTuple

from ._codec import decode, encode
from ._errors import FileFormatError, PktError
from ._model import Device, Network, parse_xml
from ._passwords import md5_crypt

_TICKED, _PARTLY = "2", "1"
_SUCCEED, _FAIL = "3", "2"  # PDU TEST_CONDITION in the answer network
# leaf -> (eclass, component), as the wizard wrote them
_LEAVES = {
    "Host Name": ("8", "Other"),
    "Default Gateway": ("0", "Ip"),
    "IP Address": ("0", "Ip"),
    "Subnet Mask": ("0", "Ip"),
    "Access VLAN": ("5", "Switching"),
    "Port Mode": ("8", "Other"),
    "VLAN Name": ("5", "Switching"),
    "Router ID": ("1", "Routing"),
    "Route": ("1", "Routing"),  # OSPF > Process ID n > Networks > Route<k>
    "Line": ("8", "Other"),  # IOS Configuration > Running Configuration > LINES > NNN <line>
    "Access-group In": ("2", "Acl"),
    "Access-group Out": ("2", "Acl"),
    "NAT Mode": ("3", "Nat"),
    "ACL": ("2", "Acl"),  # ACL > <list>
    "NAT Rule": ("3", "Nat"),  # NAT > Inside Source List | Inside Source Static > NAT Source Setting <k>
    "Pool": ("0", "Ip"),  # DHCP Server > Pools > Pool <name> > <leaf>
    "Excluded": ("0", "Ip"),  # DHCP Server > Excluded Addresses > <first> <last>
}
_HEADING_ECLASS = {"OSPF": "1", "VLANS": "5", "ACL": "2", "NAT": "3", "DHCP Server": "0"}  # others "8"
# leaves whose tree ID isn't their name (rich2.pka, 27 Oct 2026)
_LEAF_IDS = {"NAT Mode": "NAT", "DNS server IP": "DNS Server"}
_POOL_LEAVES = {"Network Address": "network", "Default Gateway": "default-router", "DNS server IP": "dns-server"}
_NAT_RULES = {"Inside Source List": "list", "Inside Source Static": "static"}
_CONFIG = ("IOS Configuration", "Running Configuration", "LINES")
_NOT_IN_NETS_1_2 = ("PIXMAPBANK", "MOVIEBANK", "COMMAND_LOGS")
_AT_ACTIVITY_LEVEL = ("CEPS", "EXT_PORT_MGR")


@dataclass(frozen=True)
class Item:
    """One assessment item: where it is in the wizard's tree (device first,
    e.g. ("R1", "Ports", "GigabitEthernet0/0", "IP Address")), the answer's
    value, the value in the initial network, and its points. `node_id` is the
    tree's ID for the item when it isn't the item's name (config lines)."""

    path: tuple[str, ...]
    expected: str
    initial: str
    points: int = 1
    component: str = ""
    node_id: str = ""

    def __str__(self) -> str:
        return f"{' > '.join(self.path)} = {self.expected}"


class Test(NamedTuple):
    """A connectivity test: a ping from `source` to `destination` that
    should succeed (or, with succeed=False, fail)."""

    source: str
    destination: str
    succeed: bool = True


@dataclass
class Activity:
    initial: Network
    answer: Network
    instructions: list[str]
    items: list[Item]
    tests: list[Test] = field(default_factory=list)

    def score(self, net: Network) -> list[tuple[Item, bool | None]]:
        """Each item with whether `net` matches the answer: True, False, or
        None for a kind of item pktlib can't read. Connectivity tests need the
        simulation, so they aren't scored here."""
        out: list[tuple[Item, bool | None]] = []
        for item in self.items:
            got = _value(net, item.path, item.node_id)
            out.append((item, None if got is None else got == item.expected))
        return out

    def to_xml(self) -> bytes:
        """The activity's XML. Every item must be a kind pktlib can write."""
        unknown = [" > ".join(i.path) for i in self.items if _kind(i.path) is None]
        if unknown:
            raise PktError(f"pktlib can't write these items yet: {', '.join(unknown)}")
        root = parse_xml(
            gzip.decompress(resources.files("pktlib").joinpath("data").joinpath("activity.xml.gz").read_bytes())
        )
        slots = root.findall("PACKETTRACER5")
        for i, (slot, net) in enumerate(zip(slots, (self.initial, self.initial, self.answer), strict=True)):
            src = parse_xml(net.to_xml())
            for child in src:
                if child.tag in _AT_ACTIVITY_LEVEL or (i and child.tag in _NOT_IN_NETS_1_2):
                    continue
                slot.append(child)
            if i == 0:  # the first network carries the (empty) image banks, as the wizard wrote it
                for at, tag in enumerate(("PIXMAPBANK", "MOVIEBANK"), 1):
                    if slot.find(tag) is None:
                        slot.insert(at, ET.Element(tag))
        _mark_tests(slots[2], self.tests)
        for tag, values in (("COMPARISONS", "expected"), ("INITIALSETUP", "initial")):
            tree = root.find(tag)
            if tree is None:
                raise FileFormatError(f"the activity template has no {tag}")
            _fill(tree, [(i, getattr(i, values)) for i in self.items])
            # Packet Tracer refused a tree written without whitespace between its
            # elements as "not compatible" (27 Oct 2026); indented, it opened
            ET.indent(tree, space=" ", level=1)
        pages = root.find("ACTIVITY/INSTRUCTIONS")
        if pages is not None:
            template = pages.find("PAGE")
            for p in pages.findall("PAGE"):
                pages.remove(p)
            for text in self.instructions or [""]:
                page = copy.deepcopy(template) if template is not None else ET.Element("PAGE")
                page.text = text
                pages.append(page)
        xml: bytes = ET.tostring(root, encoding="utf-8")
        return xml

    def save(self, path: str | os.PathLike[str]) -> None:
        """Write the .pka file."""
        Path(path).write_bytes(encode(self.to_xml()))


def make_activity(
    answer: Network,
    initial: Network,
    items: Iterable[str | Sequence[str]],
    instructions: str | Sequence[str] = "",
    *,
    tests: Iterable[tuple[str, str] | tuple[str, str, bool]] = (),
    points: int = 1,
) -> Activity:
    """An activity: students start from `initial`, and each item is checked
    against `answer`. An item is a path into the wizard's tree, as a tuple or
    as "R1 > Ports > GigabitEthernet0/0 > IP Address" (see the module's list).
    Each test is (source, destination[, should succeed]); it becomes a ping in
    the answer network's first scenario."""
    built = []
    for raw in items:
        path = tuple(s.strip() for s in raw.split(">")) if isinstance(raw, str) else tuple(raw)
        tree_path, node_id = _tree_path(answer, path)
        want, start = _value(answer, tree_path, node_id), _value(initial, tree_path, node_id)
        if want is None or start is None:
            raise PktError(f"{' > '.join(path)}: no such device or port in both networks")
        built.append(Item(tree_path, want, start, points, _LEAVES[_kind(tree_path) or ""][1], node_id))
    pages = [instructions] if isinstance(instructions, str) else list(instructions)
    checks = [Test(t[0], t[1], bool(t[2]) if len(t) > 2 else True) for t in tests]
    if checks:
        answer = Network.from_bytes(answer.to_bytes(), strict=False)
        first = answer.root.findtext("SCENARIOSET/SCENARIO/NAME")
        have = [(p.source, p.destination) for p in answer.pdus if p.scenario == first]
        for t in checks:  # a ping the lab already has is used as it is
            if (t.source, t.destination) in have:
                have.remove((t.source, t.destination))
            else:
                answer.ping(t.source, t.destination)
    return Activity(initial, answer, pages, built, checks)


def load_activity(path: str | os.PathLike[str]) -> Activity:
    """Open a .pka."""
    return activity_from_xml(decode(Path(path).read_bytes()))


def activity_from_xml(xml: bytes | str) -> Activity:
    root = parse_xml(xml)
    if root.tag != "PACKETTRACER5_ACTIVITY":
        raise FileFormatError(f"not an activity: the file's root is <{root.tag}>, not <PACKETTRACER5_ACTIVITY>")
    nets = root.findall("PACKETTRACER5")
    if len(nets) != 3:
        raise FileFormatError(f"an activity should hold 3 networks; this one has {len(nets)}")
    initial, answer = (Network(copy.deepcopy(n), strict=False) for n in nets[1:])
    pages = [p.text or "" for p in root.iterfind("ACTIVITY/INSTRUCTIONS/PAGE")]
    starts = {path: value for path, value, *_ in _leaves(root.find("INITIALSETUP"), ticked_only=False)}
    items = []
    for path, value, points, component, node_id in _leaves(root.find("COMPARISONS"), ticked_only=True):
        # the wizard leaves out of INITIALSETUP what the start hasn't got (an ACL, a
        # pool, NAT on a port: rich2.pka), so read those from the initial network
        start = starts.get(path)
        if start is None:
            start = _value(initial, path, node_id) or ""
        items.append(Item(path, value, start, points, component, node_id))
    return Activity(initial, answer, pages, items, _tests(nets[2], answer))


_SWITCHES = {"Switch", "MultiLayerSwitch"}
_DEFAULT_VLANS = {1, 1002, 1003, 1004, 1005}
# config lines that differ between any two builds, or say nothing
_NOISE = re.compile(r"^(!|end|version |license udi |no service timestamps|$)")
_GRADED_BLOCKS = ("interface ", "router ospf ", "vlan ", "hostname ")  # other kinds grade these


def _candidates(nets: Sequence[Network]) -> list[tuple[str, ...]]:
    """Every item path pktlib can grade, over the devices of the first network."""
    first = nets[0]
    out: list[tuple[str, ...]] = []
    for d in first.devices:
        name = d.name
        others = [n.device(name) for n in nets[1:] if name in n]
        if d.has_ios:
            out.append((name, "Host Name"))
        elif d.ports:
            out.append((name, "Default Gateway"))
        for port in d.ports:
            addressed = any(_value(n, (name, "Ports", port, "IP Address")) not in (None, "0.0.0.0") for n in nets)
            if addressed and d.kind not in _SWITCHES:
                out += [(name, "Ports", port, "IP Address"), (name, "Ports", port, "Subnet Mask")]
            if d.kind in _SWITCHES:
                out += [(name, "Ports", port, "Access VLAN"), (name, "Ports", port, "Port Mode")]
        vlans = set(d.vlans).union(*(o.vlans for o in others)) - _DEFAULT_VLANS
        out += [(name, "VLANS", f"VLAN {v}", "VLAN Name") for v in sorted(vlans)]
        for proc in sorted(
            {
                line.split()[2]
                for x in (d, *others)
                for line in x.running_config
                if line.startswith("router ospf ") and len(line.split()) == 3
            }
        ):
            out.append((name, "OSPF", f"Process ID {proc}", "Router ID"))
            counts = [
                len([t for t in _ospf_block(x.running_config, proc) or [] if t.startswith("network ")])
                for x in (d, *others)
            ]
            out += [(name, "OSPF", f"Process ID {proc}", "Networks", f"Route{k}") for k in range(max(counts))]
        if d.has_ios:
            out += _ios_candidates(name, (d, *others))
    return out


def _ios_candidates(name: str, devs: Sequence[Device]) -> list[tuple[str, ...]]:
    """ACL, NAT and DHCP items for one router, over its copies in each network."""
    out: list[tuple[str, ...]] = []
    rcs = [x.running_config for x in devs]
    ports = sorted(
        {
            t.split(maxsplit=1)[1]
            for rc in rcs
            for i, t in enumerate(rc)
            if t.startswith("interface ")
            and any(u.startswith(("ip access-group ", "ip nat ")) for u in _block(rc[i:], t) or [])
        }
    )
    for port in ports:
        out += [(name, "Ports", port, leaf) for leaf in ("Access-group In", "Access-group Out", "NAT Mode")]
    acls = {t.split()[1] for rc in rcs for t in rc if t.startswith("access-list ")}
    acls |= {t.split()[3] for rc in rcs for t in rc if re.match(r"ip access-list (standard|extended) \S+$", t)}
    out += [(name, "ACL", a) for a in sorted(acls)]
    statics = max(len(_nat_rules(x, "static")) for x in devs)
    out += [(name, "NAT", "Inside Source Static", f"NAT Source Setting {k}") for k in range(1, statics + 1)]
    pools = sorted({t.split()[3] for rc in rcs for t in rc if re.match(r"ip dhcp pool \S+$", t)})
    out += [(name, "DHCP Server", "Pools", f"Pool {p}", leaf) for p in pools for leaf in _POOL_LEAVES]
    excluded = {t.split(maxsplit=3)[3] for rc in rcs for t in rc if re.match(r"ip dhcp excluded-address \S+ \S+$", t)}
    out += [(name, "DHCP Server", "Excluded Addresses", e) for e in sorted(excluded)]
    return out


def _graded_elsewhere(header: str | None, line: str) -> bool:
    """Whether another item kind grades this config line (so it isn't graded twice).
    `ip nat inside source list` stays a line: the wizard's item ignores `overload`."""
    if (header or "").startswith(_GRADED_BLOCKS):
        return True
    text = line.strip()
    if header is None or not line.startswith(" "):
        return (
            text.startswith(("access-list ", "ip access-list ", "ip dhcp pool "))
            or re.fullmatch(r"ip dhcp excluded-address \S+ \S+", text) is not None
            or re.fullmatch(r"ip nat inside source static \S+ \S+", text) is not None
        )
    if header.startswith("ip access-list "):
        return True
    return header.startswith("ip dhcp pool ") and text.startswith(tuple(v + " " for v in _POOL_LEAVES.values()))


def diff_items(answer: Network, start: Network) -> list[tuple[str, ...]]:
    """The items that tell `start` from `answer`: every gradable value that
    differs between them, plus the answer's config lines the start lacks.
    Lines in blocks the other kinds already grade (interfaces, `router ospf`,
    `vlan`, `hostname`) are left out, so a fault isn't counted twice, and so
    are licence serials and the like."""
    items = []
    for path in _candidates([answer, start]):
        want, got = _value(answer, path), _value(start, path)
        if want is not None and got is not None and want != got:
            items.append(path)
    for d in answer.devices:
        if not d.has_ios or d.name not in start:
            continue
        rc_start = start.device(d.name).running_config
        header = None
        for line in d.running_config:
            if not line.startswith(" "):
                header = line
            if _NOISE.match(line.strip()) or _graded_elsewhere(header, line):
                continue
            if line.startswith(" "):
                if header is not None and _find_line(rc_start, header, line) is None:
                    items.append((d.name, "Running Configuration", header, line.strip()))
            elif _find_line(rc_start, None, line) is None:
                items.append((d.name, "Running Configuration", line))
    return items


# --- the tree -----------------------------------------------------------------


def _leaves(tree: ET.Element | None, *, ticked_only: bool) -> list[tuple[tuple[str, ...], str, int, str, str]]:
    """(path below "Network", value, points, component, ID) for every leaf."""
    out: list[tuple[tuple[str, ...], str, int, str, str]] = []

    def walk(node: ET.Element, path: tuple[str, ...]) -> None:
        name = node.find("NAME")
        here = path + ((name.text or "") if name is not None else "",)
        if name is not None and node.find("NODE") is None and (not ticked_only or name.get("checkType") == _TICKED):
            points = node.findtext("POINTS") or "0"
            node_id = node.findtext("ID") or ""
            out.append(
                (
                    here[1:],
                    name.get("nodeValue", ""),
                    int(points) if points.isdigit() else 0,
                    node.findtext("COMPONENTS") or "",
                    node_id if node_id != here[-1] else "",
                )
            )
        for child in node.findall("NODE"):
            walk(child, here)

    for top in [] if tree is None else tree.findall("NODE"):
        walk(top, ())
    return out


def _kind(path: tuple[str, ...]) -> str | None:
    """Which leaf kind a tree path is, or None."""
    if len(path) < 2:
        return None
    if path[1:4] == _CONFIG and len(path) == 5:
        return "Line"
    if path[1] == "OSPF" and len(path) == 5 and path[3] == "Networks" and re.fullmatch(r"Route\d+", path[4]):
        return "Route"
    if path[1] == "ACL" and len(path) == 3:
        return "ACL"
    if path[1] == "NAT" and len(path) == 4 and path[2] in _NAT_RULES:
        return "NAT Rule" if re.fullmatch(r"NAT Source Setting [1-9]\d*", path[3]) else None
    if path[1:3] == ("DHCP Server", "Pools") and len(path) == 5 and path[3].startswith("Pool "):
        return "Pool" if path[4] in _POOL_LEAVES else None
    if path[1:3] == ("DHCP Server", "Excluded Addresses") and len(path) == 4:
        return "Excluded"
    leaf = path[-1]
    shapes = {
        "Host Name": len(path) == 2,
        "Default Gateway": len(path) == 2,
        "IP Address": len(path) == 4 and path[1] == "Ports",
        "Subnet Mask": len(path) == 4 and path[1] == "Ports",
        "Access VLAN": len(path) == 4 and path[1] == "Ports",
        "Port Mode": len(path) == 4 and path[1] == "Ports",
        "Access-group In": len(path) == 4 and path[1] == "Ports",
        "Access-group Out": len(path) == 4 and path[1] == "Ports",
        "NAT Mode": len(path) == 4 and path[1] == "Ports",
        "VLAN Name": len(path) == 4 and path[1] == "VLANS" and re.fullmatch(r"VLAN \d+", path[2]) is not None,
        "Router ID": len(path) == 4 and path[1] == "OSPF" and re.fullmatch(r"Process ID \d+", path[2]) is not None,
    }
    return leaf if shapes.get(leaf) else None


def _tree_path(answer: Network, path: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
    """A user's item path -> (the wizard's tree path, the leaf's ID if not its name)."""
    if len(path) >= 3 and path[1] == "Running Configuration":
        dev, lines = path[0], path[2:]
        if len(lines) not in (1, 2):
            raise PktError(f"{' > '.join(path)}: give a config line, or a block header and a line in it")
        try:
            rc = answer.device(dev).running_config
        except PktError:
            raise PktError(f"{' > '.join(path)}: no device {dev!r} in the answer") from None
        header, line = (None, lines[0]) if len(lines) == 1 else (lines[0], " " + lines[1].strip())
        line = _as_shown(line)
        at = _find_line(rc, header, line)
        if at is None:
            raise PktError(f"{' > '.join(path)}: that line isn't in {dev}'s config in the answer")
        # Packet Tracer finds the line by this ID (the line, after its block's header), not
        # by the number in its name: it renumbers the config into IOS order, so pktlib's
        # numbers can be off; with a wrong number the line still graded, shown as "Item"
        node_id = line if header is None else f"{header} {line.strip()}"
        return (dev, *_CONFIG, f"{at + 1:03} {line}"), node_id
    if path[1:2] == ("Routes",):
        raise PktError(
            f"{' > '.join(path)}: Packet Tracer 8.2's wizard can't grade static routes; "
            "use a Running Configuration line (R1 > Running Configuration > ip route ...)"
        )
    kind = _kind(path)
    if kind is None:
        raise PktError(f"pktlib can't write {' > '.join(path)!r} yet (see pktlib.activity for the kinds it knows)")
    if kind == "NAT Rule":
        return path, _nat_rule_id(answer, path)
    leaf = path[len(path) - 1]
    return path, _LEAF_IDS.get(leaf, "") if kind in ("NAT Mode", "Pool") else ""


def _nat_rule_id(answer: Network, path: tuple[str, ...]) -> str:
    """The tree ID of NAT > <kind> > NAT Source Setting <k>: the answer's k-th rule's."""
    dev, _, which, setting = path
    try:
        rules = _nat_rules(answer.device(dev), _NAT_RULES[which])
    except PktError:
        raise PktError(f"{' > '.join(path)}: no device {dev!r} in the answer") from None
    k = int(setting.split()[-1])
    if k > len(rules):
        raise PktError(f"{' > '.join(path)}: the answer's {dev} has {len(rules)} such NAT rules")
    return rules[k - 1][0]


def _node(
    name: str,
    node_id: str,
    eclass: str,
    *,
    value: str = "",
    leaf: bool = False,
    device: bool = False,
    points: int = 1,
    component: str = "",
) -> ET.Element:
    """One tree node, with the attributes the wizard wrote."""
    node = ET.Element("NODE")
    attrs = {"eclass": eclass, "checkType": _TICKED if leaf else _PARTLY}
    if device:
        attrs["translate"] = "true"
    attrs |= {
        "variableName": "",
        "incorrectFeedback": "",
        "headNode": "false" if leaf else "true",
        "variableEnabled": "true" if leaf else "false",
        "obfuscateName": "false",
        "overrideDBGrading": "false",
        "nodeValue": value,
    }
    ET.SubElement(node, "NAME", attrs).text = name
    ET.SubElement(node, "ID", {"translate": "true"} if device else {}).text = node_id
    ET.SubElement(node, "COMPONENTS").text = component if leaf else None
    ET.SubElement(node, "POINTS").text = str(points) if leaf else None
    return node


def _heading_id(path: tuple[str, ...], depth: int) -> str:
    """A heading's ID: its name, except "Process ID 1" and "VLAN 10" (just the
    number) and "Pool LAN" (just the pool's name)."""
    name = path[depth]
    if depth == 2 and path[1] in ("OSPF", "VLANS"):
        return name.split()[-1]
    if depth == 3 and path[1:3] == ("DHCP Server", "Pools"):
        return name[len("Pool ") :]
    return name


def _fill(tree: ET.Element, items: list[tuple[Item, str]]) -> None:
    """Write the tree under `tree`: a "Network" heading, then each item's path."""
    top = _node("Network", "Network", "8")
    tree.insert(0, top)
    for item, value in items:
        path, kind, leaf = item.path, _kind(item.path) or "", item.path[-1]
        eclass = _HEADING_ECLASS.get(path[1], "8") if len(path) > 2 else "8"
        parent = top
        for depth, name in enumerate(path[:-1]):
            found = next((n for n in parent.findall("NODE") if n.findtext("NAME") == name), None)
            if found is None:
                found = _node(name, _heading_id(path, depth), "8" if depth == 0 else eclass, device=depth == 0)
                parent.append(found)
            parent = found
        leaf_eclass, component = _LEAVES[kind]
        parent.append(
            _node(
                leaf,
                item.node_id or leaf,
                leaf_eclass,
                value=value,
                leaf=True,
                points=item.points,
                component=item.component or component,
            )
        )


# --- values -------------------------------------------------------------------


# Packet Tracer shows a secret as type 5 with the salt mERr, whatever was typed
# (`enable secret class12345` showed as `enable secret 5 $1$mERr$8BPX...`, 27 Oct 2026)
_SECRET = re.compile(r"^(\s*(?:enable|username \S+(?: privilege \d+)?) secret) (?!5 )(\S+)$")


def _as_shown(line: str) -> str:
    """A config line as Packet Tracer's running config shows it."""
    m = _SECRET.match(line)
    return f"{m[1]} 5 {md5_crypt(m[2], 'mERr')}" if m else line


def _find_line(rc: list[str], header: str | None, line: str) -> int | None:
    """Index of `line` in a running config: a top-level line, or one inside the
    block that `header` opens."""
    line = _as_shown(line).rstrip()
    inside = header is None
    for i, text in enumerate(rc):
        if not text.startswith(" "):
            if header is None and _as_shown(text) == line:
                return i
            inside = text == header
        elif inside and header is not None and _as_shown(text).rstrip() == line:
            return i
    return None


def _block(rc: list[str], header: str) -> list[str] | None:
    """The lines inside the block `header` opens, stripped, or None if there's no such block."""
    body: list[str] = []
    found = False
    for text in rc:
        if not text.startswith(" "):
            if found:
                break
            found = text.rstrip() == header
        elif found:
            body.append(text.strip())
    return body if found else None


def _ospf_block(rc: list[str], process: str) -> list[str] | None:
    return _block(rc, f"router ospf {process}")


def _acl_lines(rc: list[str], name: str) -> list[str]:
    """An access list's lines, as the wizard joins them: `access-list 110 ...` lines
    without the prefix, else the body of `ip access-list standard|extended <name>`."""
    prefix = f"access-list {name} "
    lines = [t[len(prefix) :].rstrip() for t in rc if t.startswith(prefix)]
    for way in ("standard", "extended"):
        lines += _block(rc, f"ip access-list {way} {name}") or []
    return lines


def _nat_rules(d: Device, which: str) -> list[tuple[str, str]]:
    """(tree ID, value) for each `ip nat inside source list|static` rule, in order.
    A list rule is ID the list's number, value the interface's full name; a static
    one is ID and value "<local> <global> ", the trailing space as Packet Tracer
    wrote it (rich2.pka, 27 Oct 2026). Forms not seen there are left out."""
    out = []
    for text in d.running_config:
        words = text.split()
        if words[:5] != ["ip", "nat", "inside", "source", which]:
            continue
        if which == "list" and len(words) >= 8 and words[6] == "interface":
            try:
                port = d.port(words[7]).name
            except PktError:
                port = words[7]
            out.append((words[5], port))
        elif which == "static" and len(words) == 7:
            pair = f"{words[5]} {words[6]} "
            out.append((pair, pair))
    return out


def _router_id(d: Device, body: list[str]) -> str:
    """OSPF's router ID as Packet Tracer shows it: `router-id`, else the
    highest loopback address, else the highest address on an up interface."""
    for text in body:
        if text.startswith("router-id "):
            return text.split()[1]
    ifaces = d.interfaces
    loops = [ipaddress.IPv4Interface(i.address).ip for n, i in ifaces.items() if n.startswith("Loopback") and i.address]
    if loops:
        return str(max(loops))
    ups = [ipaddress.IPv4Interface(i.address).ip for i in ifaces.values() if i.address and i.up]
    return str(max(ups)) if ups else ""


def _value(net: Network, path: tuple[str, ...], node_id: str = "") -> str | None:
    """The value an item reads from `net`, as the wizard shows it, or None if
    pktlib can't read that item (or the device or port isn't there)."""
    kind = _kind(path)
    if kind is None:
        return None
    try:
        d = net.device(path[0])
    except PktError:
        return None
    if kind == "Line":
        text = path[-1][4:]
        header = None
        if text.startswith(" ") and node_id.endswith(text.strip()):
            header = node_id[: -len(text.strip())].rstrip()
        return text if _find_line(d.running_config, header, text) is not None else ""
    if kind == "Host Name":
        return d.hostname
    if kind == "Default Gateway":
        return None if d.has_ios else (d.gateway or "0.0.0.0")
    if kind in ("Access VLAN", "Port Mode"):
        try:
            port = d.port(path[2])
        except PktError:
            return None
        if kind == "Port Mode":  # the wizard showed 0 for a trunk, 1 for access or unset
            return "0" if port.mode == "trunk" else "1"
        return str(port.access_vlan or 1)
    if kind == "VLAN Name":
        return d.vlans.get(int(path[2].split()[-1]), "")
    if kind in ("Router ID", "Route"):
        body = _ospf_block(d.running_config, path[2].split()[-1])
        if body is None:
            return ""
        if kind == "Router ID":
            return _router_id(d, body)
        nets = [t.split() for t in body if t.startswith("network ")]
        k = int(path[4][len("Route") :])
        return f"{nets[k][1]} {nets[k][2]} {nets[k][4]}" if k < len(nets) and len(nets[k]) >= 5 else ""
    rc = d.running_config
    if kind == "ACL":
        return "\n".join(_acl_lines(rc, path[2]))
    if kind == "NAT Rule":
        rules = _nat_rules(d, _NAT_RULES[path[2]])
        if node_id:  # Packet Tracer finds the rule by its ID: the list's number, or the static pair
            return next((value for rid, value in rules if rid == node_id), "")
        k = int(path[3].split()[-1])
        return rules[k - 1][1] if k <= len(rules) else ""
    if kind == "Pool":
        body = _block(rc, f"ip dhcp pool {path[3][len('Pool ') :]}") or []
        key = _POOL_LEAVES[path[4]] + " "
        return next((t.split()[1] for t in body if t.startswith(key)), "")
    if kind == "Excluded":
        return path[3] if f"ip dhcp excluded-address {path[3]}" in rc else ""
    if kind in ("Access-group In", "Access-group Out", "NAT Mode"):
        if path[2] not in d.ports and path[2] not in d.interfaces:
            return None
        body = _block(rc, f"interface {path[2]}") or []
        if kind == "NAT Mode":  # the wizard showed 1 inside, 2 outside, 0 neither
            return "1" if "ip nat inside" in body else "2" if "ip nat outside" in body else "0"
        way = " in" if kind == "Access-group In" else " out"
        return next((t.split()[2] for t in body if t.startswith("ip access-group ") and t.endswith(way)), "")
    # IP Address / Subnet Mask
    if d.has_ios:
        if path[2] not in d.ports and path[2] not in d.interfaces:
            return None
        iface = d.interfaces.get(path[2])
        addr = iface.address if iface else None
    else:
        try:
            addr = d.port(path[2]).address
        except PktError:
            return None
    if not addr:
        return "0.0.0.0"
    i = ipaddress.IPv4Interface(addr)
    return str(i.ip if kind == "IP Address" else i.netmask)


# --- connectivity tests -------------------------------------------------------


def _first_scenario_pdus(net_el: ET.Element) -> list[ET.Element]:
    first = net_el.find("SCENARIOSET/SCENARIO")
    return [] if first is None else first.findall("PDU")


def _mark_tests(answer_el: ET.Element, tests: list[Test]) -> None:
    """Set TEST_CONDITION on the answer's first-scenario PDUs that match a test."""
    names = {e.findtext("SAVE_REF_ID") or "": e.findtext("NAME") or "" for e in answer_el.iter("ENGINE")}
    todo = list(tests)
    for pdu in _first_scenario_pdus(answer_el):
        dst = pdu.find("DESTINATION")
        pair = (names.get(pdu.findtext("SOURCE") or ""), names.get(dst.get("device", "") if dst is not None else ""))
        match = next((t for t in todo if (t.source, t.destination) == pair), None)
        cond = pdu.find("TEST_CONDITION")
        if match is not None and cond is not None:
            cond.text = _SUCCEED if match.succeed else _FAIL
            todo.remove(match)
    # Check Results listed only the tests ahead of the first untested ping in the
    # scenario (27 Oct 2026), so the tested ones go first
    scenario = answer_el.find("SCENARIOSET/SCENARIO")
    if scenario is not None:
        pdus = scenario.findall("PDU")
        tested = [p for p in pdus if p.findtext("TEST_CONDITION") in (_SUCCEED, _FAIL)]
        if tested:
            at = list(scenario).index(pdus[0])
            for p in pdus:
                scenario.remove(p)
            for i, p in enumerate(tested + [p for p in pdus if p not in tested]):
                scenario.insert(at + i, p)


def _tests(answer_el: ET.Element, answer: Network) -> list[Test]:
    names = {d.ref: d.name for d in answer.devices}
    out = []
    for pdu in _first_scenario_pdus(answer_el):
        cond = pdu.findtext("TEST_CONDITION")
        if cond in (_SUCCEED, _FAIL):
            dst = pdu.find("DESTINATION")
            out.append(
                Test(
                    names.get(pdu.findtext("SOURCE") or "", "?"),
                    names.get(dst.get("device", "") if dst is not None else "", "?"),
                    cond == _SUCCEED,
                )
            )
    return out
