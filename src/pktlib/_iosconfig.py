"""Reading IOS config text the way Packet Tracer replays it."""

from __future__ import annotations

import contextlib
import re

from ._errors import PktError
from ._ports import canonical_port, expand_range, port_sort_key


def _norm_header(line: str) -> str:
    """'interface fa0/0' -> 'interface FastEthernet0/0' so the same interface
    written two ways is one block. Anything else is left alone."""
    if line.lower().startswith("interface "):
        try:
            return "interface " + canonical_port(line.split(None, 1)[1])
        except PktError:
            return line
    return line


def blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Config text -> [(header, body)]; top-level one-liners have an empty body.
    A header seen twice (default block, then one added later) merges into the
    first, so the result reflects what replaying the text in order gives."""
    out: list[tuple[str, list[str]]] = []
    index: dict[str, int] = {}
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        if line.strip() in ("", "!") or line.startswith(" "):
            continue
        body = []
        while i < len(lines) and lines[i].startswith(" "):
            body.append(lines[i].strip())
            i += 1
        headers = [line]
        if line.lower().startswith("interface range "):
            with contextlib.suppress(PktError):  # not a range IOS takes: kept as written
                headers = ["interface " + n for n in expand_range(line.split(None, 2)[2])]
        for h in headers:
            h = _norm_header(h)
            key = " ".join(h.lower().split())
            if key in index:
                out[index[key]][1].extend(body)
                continue
            index[key] = len(out)
            out.append((h, list(body)))
    return out


# Config Packet Tracer 8.2 is known not to take from a file, each seen in the
# GUI. A refused line is dropped silently on load; the rest of the config runs.
_REFUSED = [
    (
        re.compile(r"^\s*default-information originate\b.*\b(metric|metric-type)\b"),
        "is refused by Packet Tracer 8.2 (only plain `default-information originate`), so no default is sent",
    ),
    (
        re.compile(r"^interface range ", re.I),
        "is ignored when Packet Tracer loads a file; write one block per interface",
    ),
]


def refused(lines: list[str]) -> list[tuple[str, str]]:
    """Lines Packet Tracer 8.2 won't apply on load, with why: [(line, reason)]."""
    return [(line, why) for line in lines for rx, why in _REFUSED if rx.search(line)]


_MERGEABLE = (
    "interface ",
    "line ",
    "router ",
    "ip dhcp pool ",
    "ip access-list ",
    "route-map ",
    "crypto isakmp policy ",
    "crypto map ",
    "class-map ",
    "policy-map ",
    "zone-pair ",
)
# Blocks interface lines refer to by name: a zone for `zone-member security`,
# a rule for `ip ips ... in`, a map for `crypto map`. IOS saves them ahead of
# the interfaces, and since Packet Tracer replays the file in order, that is
# where a new one goes, each after the last.
_BEFORE_INTERFACES = ("crypto ", "class-map ", "policy-map ", "zone ", "zone-pair ", "ip ips ")
# Global switches that interface lines depend on: written ahead of the first
# interface, where IOS saves them. Packet Tracer replays the file in order, and
# with `ipv6 unicast-routing` written near the end it refused every
# `ipv6 ospf` / `ipv6 eigrp` interface line (8.2, found by the stress tests).
_EARLY = ("ipv6 unicast-routing",)
# top-level settings with one value: a new one replaces the old line in place
_SINGLE = (
    "hostname ",
    "spanning-tree mode ",
    "ip domain-name ",
    "enable secret ",
    "enable password ",
    "vtp mode ",
    "vtp domain ",
    "banner motd ",
    "banner login ",
    "security passwords min-length ",
)


def _key(header: str) -> str:
    return " ".join(_norm_header(header).lower().split())


# settings inside a block that hold one value: a new one replaces the old line
_ONE_VALUE = {
    "password",
    "exec-timeout",
    "description",
    "bandwidth",
    "speed",
    "duplex",
    "clock",
    "encapsulation",
    "login",
}
_ONE_VALUE_2 = {("switchport", "mode"), ("transport", "input")}
_ONE_VALUE_3 = {("switchport", "access", "vlan"), ("switchport", "voice", "vlan"), ("switchport", "trunk", "native")}


def _replaces(new: str, old: str) -> bool:
    """Whether `new` takes the place of `old` inside a block, as re-entering it
    in IOS would: a second `password` replaces the first, `no shutdown`
    replaces `shutdown`, an address replaces `no ip address`."""

    def kind(line: str) -> str | None:
        w = line.split()
        if not w:
            return None
        if w in (["shutdown"], ["no", "shutdown"]):
            return "shutdown"
        if w == ["no", "ip", "address"] or (w[:2] == ["ip", "address"] and "secondary" not in w):
            return "ip address"
        if w[0] in _ONE_VALUE:
            return w[0]
        if tuple(w[:2]) in _ONE_VALUE_2:
            return " ".join(w[:2])
        if tuple(w[:3]) in _ONE_VALUE_3:
            return " ".join(w[:3])
        return None

    k = kind(new)
    return k is not None and k == kind(old)


def merge_config(lines: list[str], commands: list[str]) -> list[str]:
    """Add config-mode `commands` to a running config the way IOS would save it.

    A block whose header is already there (`interface Fa0/23`, `line vty 0 4`,
    `router ospf 1`) goes into that block, replacing its `shutdown` or `no ip
    address`; a new `interface Port-channel`, or a crypto, zone, class-map,
    policy-map or `ip ips` block, goes ahead of the other interfaces;
    anything else goes before `end`. Packet Tracer's loader doesn't always
    honour a second copy of a block: a `channel-group` in an interface block
    repeated at the end was dropped (8.2, 25 Oct 2026). A one-line command
    already there is not added again."""
    lines = list(lines)
    added = False

    def before_end(block: list[str]) -> None:
        end = len(lines) - 1 - lines[::-1].index("end") if "end" in lines else len(lines)
        lines[end:end] = block

    i = 0
    while i < len(commands):
        header = commands[i]
        i += 1
        body = []
        while i < len(commands) and commands[i].startswith(" "):
            body.append(commands[i])
            i += 1
        if header.startswith(" "):  # stray body line with no header
            before_end([header] + body)
            added = True
            continue
        header = _norm_header(header)
        if header in _EARLY and not body:
            if header not in lines:
                first = next((j for j, line in enumerate(lines) if line.startswith("interface ")), len(lines))
                lines[first:first] = [header, "!"]
            continue
        if not body and not header.lower().startswith(_MERGEABLE):
            # a top-level switch replaces its own `no` form (and the other way round)
            opposite = header[3:] if header.startswith("no ") else "no " + header
            if opposite in lines:
                lines[lines.index(opposite)] = header
                continue
        single = next((k for k in _SINGLE if header.startswith(k)), None)
        if single and not body:
            old_at = next((j for j, line in enumerate(lines) if line.startswith(single)), None)
            if old_at is not None:
                lines[old_at] = header
                continue
        at = None
        if header.lower().startswith(_MERGEABLE):
            at = next(
                (j for j, line in enumerate(lines) if not line.startswith(" ") and _key(line) == _key(header)), None
            )
        if at is None and not body and header != "!":
            # the same one-line command again: IOS keeps one line (a `!` is a comment, kept as typed).
            # A block outside _MERGEABLE entered again still gets a second copy, as the examples were
            # checked in Packet Tracer that way; see TODO.md.
            same = " ".join(header.split())
            if any(not line.startswith(" ") and " ".join(line.split()) == same for line in lines):
                continue
        if at is None and header.startswith(_BEFORE_INTERFACES):
            first_iface = next((j for j, line in enumerate(lines) if line.startswith("interface ")), None)
            if first_iface is not None:
                lines[first_iface:first_iface] = [header] + body + ["!"]
                continue
        if at is None and header.startswith("interface Port-channel"):
            # where Packet Tracer saves it, ahead of the member ports; left after
            # them, the channel still forms but `router ospf` later in the same
            # config is silently dropped on load (8.2, 25 Oct 2026)
            # and among the port-channels, in number order as IOS saves them (a second one used
            # to go ahead of the first; found writing the CCNA EtherChannel example)
            number = port_sort_key(header.split(None, 1)[1])
            first = next(
                (
                    j
                    for j, line in enumerate(lines)
                    if line.startswith("interface ")
                    and not (
                        line.startswith("interface Port-channel") and port_sort_key(line.split(None, 1)[1]) < number
                    )
                ),
                len(lines),
            )
            lines[first:first] = [header] + body + ["!"]
            continue
        if at is None:
            before_end([header] + body)
            added = True
            continue
        end = at + 1
        while end < len(lines) and lines[end].startswith(" "):
            end += 1
        old = [line for line in lines[at + 1 : end] if not any(_replaces(b.strip(), line.strip()) for b in body)]
        if not any(line.startswith("  ") for line in old + body):
            # a flat block (interface, router ospf, line): a command already in it isn't added
            # again, as IOS shows it once. Repeats within what's typed now stay as typed (order
            # matters: shutdown, no shutdown, shutdown), and nested blocks (BGP address families)
            # repeat lines like ` exit-address-family` on purpose, so they're left alone.
            body = [b for b in body if b not in old]
        lines[at + 1 : end] = old + body
    if added:
        before_end(["!"])
    return lines


def setting_key(line: str) -> str:
    """What a later line would overwrite: the command without its value.
    'clock rate 64000' -> 'clock rate', 'standby 1 ip 10.0.0.1' -> 'standby 1 ip',
    'switchport access vlan 10' -> 'switchport access vlan', 'description x y' ->
    'description', 'no shutdown' -> 'shutdown'."""
    words = line.split()
    if not words:
        return ""
    if words[0] == "no":
        words = words[1:] or ["no"]
    if words[0] == "description":
        return "description"
    return (
        " ".join(words[:-1])
        if len(words) >= 3
        else words[0]
        if len(words) == 2 and words[1][:1].isdigit()
        else " ".join(words)
    )


def interface_state(body: list[str]) -> tuple[str | None, str | None, bool, dict[str, str]]:
    """Replay an interface's commands -> (ip, mask, up, other settings).
    An interface is up unless its last word on it is `shutdown`: `show run`
    leaves out `no shutdown`, and Packet Tracer writes `shutdown` on every
    router port that starts down (switch ports start up and say nothing).
    A `secondary` address is kept in the other settings, not taken as the
    primary; settings that can repeat (helper addresses) are all kept."""
    shut = False
    ip = mask = None
    rest: dict[str, str] = {}
    for b in body:
        if b == "shutdown":
            shut = True
        elif b == "no shutdown":
            shut = False
        elif b == "no ip address":
            ip = mask = None
        elif b.startswith("ip address ") and b.split()[-1] != "secondary":
            parts = b.split()
            if len(parts) >= 4:
                ip, mask = parts[2], parts[3]
        elif b in ("duplex auto", "speed auto"):
            continue
        elif b.split()[-1] == "secondary" or b.startswith(_REPEATABLE):
            rest[b] = b
        else:
            rest[setting_key(b)] = b
    return ip, mask, not shut, rest


_REPEATABLE = ("ip helper-address ",)


def interfaces(lines: list[str]) -> dict[str, tuple[str | None, str | None, bool]]:
    """Interface name -> (ip, mask, up) after replaying the config."""
    out = {}
    for header, body in blocks(lines):
        if header.startswith("interface "):
            ip, mask, up, _ = interface_state(body)
            out[header.split(None, 1)[1]] = (ip, mask, up)
    return out


# structural lines, never "set" by anyone: everything else is compared with the model's own
# factory config by to_python (a fixed list here once hid `spanning-tree mode rapid-pvst`
# and `no ip cef`, found by exporting every example)
_SKIP_TOP = re.compile(r"^(version |boot-start-marker|boot-end-marker|end$|hostname |license )")


def _interface_body(body: list[str]) -> list[str] | None:
    """An interface's commands, reduced to what differs from factory default."""
    ip, mask, up, rest = interface_state(body)
    if rest.get("clock rate") == "clock rate 2000000":
        del rest["clock rate"]
    if ip is None and not rest and not up and "shutdown" not in body:
        return None
    return ([f"ip address {ip} {mask}"] if ip else []) + list(rest.values()) + (["no shutdown"] if up else ["shutdown"])


def interesting_config(lines: list[str]) -> list[str]:
    """Drop the boilerplate a fresh device already has; keep what someone set.
    Output order is fixed (one-liners, interfaces in IOS order, other blocks)
    so a dump reads the same however the config was built up."""
    singles: list[str] = []
    ifaces: list[tuple[str, list[str]]] = []
    others: list[tuple[str, list[str]]] = []
    for header, body in blocks(lines):
        if header.startswith("interface "):
            kept = _interface_body(body)
            if kept is not None:
                ifaces.append((header, kept))
        elif header.startswith("line ") and all(b == "login" for b in body):
            continue
        elif not body:
            if not _SKIP_TOP.match(header) and not header.startswith(("router ", "line ")):
                singles.append(header)
            elif header.startswith("router "):
                others.append((header, body))
        else:
            others.append((header, body))
    ifaces.sort(key=lambda hb: port_sort_key(hb[0][len("interface ") :]))
    out = list(singles)
    for header, body in ifaces + others:
        out.append(header)
        out += [" " + b for b in body]
    return out
