"""An object model over Packet Tracer's XML: devices, ports, links, configs.

Everything reads and writes the underlying ElementTree directly, so whatever
pktlib doesn't model survives a load/save untouched.
"""

from __future__ import annotations

import copy
import difflib
import gzip
import ipaddress
import json
import math
import os
import random
import re
import textwrap
import uuid
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NamedTuple, get_args

from . import _editions as editions
from ._codec import decode_with_level, encode
from ._errors import FileFormatError, NotFound, PktError, PktWarning
from ._iosconfig import blocks, interface_state, interfaces, merge_config, refused
from ._modules import SLOT_WORDS, Slot, fresh_module, module_models, port_names_for, slots
from ._ports import _PORT_RE, _PREFIX, CABLE_TYPES, canonical_port, expand_range, is_serial, port_sort_key
from ._shapes import Note, Shape, check_note_text, make_note, make_shape
from ._xml import fmt_num, req, req_int_attr, req_text
from ._xml import set_text as _set
from ._xml import text as _text

# --- small helpers ----------------------------------------------------------

# XML 1.0 forbids most control characters, but Packet Tracer writes them raw: a
# banner's ^C delimiter is byte 0x03 (`banner motd ^Cno Entry^C`, found in a
# lecturer's starter file). They are swapped for private-use characters to get
# past the parser, then put back, so the text reads and saves as PT wrote it.
_CONTROL = bytes(c for c in range(32) if c not in (9, 10, 13))
_HIDE = {c: chr(0xE000 + c).encode() for c in _CONTROL}
_SHOW = str.maketrans({chr(0xE000 + c): chr(c) for c in _CONTROL})


def parse_xml(xml: bytes | str) -> ET.Element:
    """ET.fromstring that accepts the control characters Packet Tracer writes."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    if any(b in data for b in _CONTROL):
        data = b"".join(_HIDE.get(b, bytes((b,))) for b in data)
        root = _fromstring(data)
        for el in root.iter():
            if el.text:
                el.text = el.text.translate(_SHOW)
            if el.tail:
                el.tail = el.tail.translate(_SHOW)
            for k, v in el.attrib.items():
                el.attrib[k] = v.translate(_SHOW)
        return root
    return _fromstring(data)


def _fromstring(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise FileFormatError(f"not well-formed XML ({e})") from None


def _rand_addr(rng: random.Random) -> str:
    return str(rng.randrange(10**12, 10**13))


_MAC_RE = re.compile(r"[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}")


def _rand_mac(rng: random.Random) -> str:
    h = "%012X" % ((0x0002 << 32) | rng.getrandbits(32))
    return f"{h[0:4]}.{h[4:8]}.{h[8:12]}"


def _unique(draw: Callable[[], str], taken: set[str]) -> str:
    """draw() until it gives something not in `taken` (compared case-blind), and take it."""
    value = draw()
    while value.upper() in taken:
        value = draw()
    taken.add(value.upper())
    return value


def _link_local(mac: str) -> str:
    """The EUI-64 link-local Packet Tracer stores for a port with this MAC:
    0090.0CC7.8E5A -> FE80::290:CFF:FEC7:8E5A."""
    b = bytearray.fromhex(mac.replace(".", ""))
    b[0] ^= 0x02
    w = b[:3] + b"\xff\xfe" + b[3:]
    return "FE80::" + ":".join(f"{(w[i] << 8) | w[i + 1]:X}" for i in range(0, 8, 2))


def _refresh_link_locals(el: ET.Element) -> None:
    """Re-derive every port's stored IPv6 link-local from its MAC. Packet Tracer
    shows the stored value, so a cloned device keeps its template's (found by
    the enterprise example: eight PCs on FE80::290:CFF:FEC7:8E5A)."""
    for p in el.iter("PORT"):
        ll, mac = p.find("IPV6_LINK_LOCAL"), p.findtext("MACADDRESS")
        if ll is not None and ll.text and mac and _MAC_RE.fullmatch(mac.strip()):
            ll.text = _link_local(mac.strip())


def _mask(prefix: int) -> str:
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32:
        raise PktError(f"prefix must be 0-32, got {prefix!r}")
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def _expand_interface_ranges(commands: list[str]) -> list[str]:
    """`interface range g1/0/23 - 24` + body -> one `interface X` + body per
    port. Real IOS never saves a range (it expands it as you type), and Packet
    Tracer's file loader ignores range lines, so they must be expanded here."""
    out: list[str] = []
    i = 0
    while i < len(commands):
        c = commands[i]
        i += 1
        if not c.lower().startswith("interface range "):
            out.append(c)
            continue
        body = []
        while i < len(commands) and commands[i].startswith(" "):
            body.append(commands[i])
            i += 1
        for name in expand_range(c.split(None, 2)[2]):
            out.append(f"interface {name}")
            out += body
    return out


_MODE_LINE = re.compile(r"(exit|end|conf(igure)?(\s+t(erminal)?)?)", re.I)


# block headers that mean nothing alone: IOS says "% Incomplete command"
_NEEDS_A_NAME = {
    "interface": "a name: interface g0/0",
    "router": "a protocol: router ospf 1",
    "line": "a line: line vty 0 4",
}


def _abbrev(word: str, full: str) -> bool:
    """IOS shorthand: `sw` for switchport, `acc` for access (two letters at least)."""
    return len(word) >= 2 and full.startswith(word)


def _prepare_commands(commands: Iterable[str]) -> list[str]:
    """Config lines as IOS would save them: one command per line, tabs as
    spaces, no blank lines or mode changes, `ip address` in IOS's own form."""
    if isinstance(commands, (bytes, dict)) or not isinstance(commands, Iterable):
        raise TypeError(f"commands are a string or a list of strings, got {type(commands).__name__}")
    out: list[str] = []
    for item in commands:
        _check_str(item, "a config line")
        for raw in item.splitlines():
            line = re.sub(r"^[ \t]+", lambda m: m.group().replace("\t", " "), raw).rstrip()
            if not line.strip() or _MODE_LINE.fullmatch(line.strip()):
                continue
            if not out:
                line = line.lstrip()  # nothing to be the body of yet: a global command
            words = line.split()
            if len(words) == 1 and not line.startswith(" ") and words[0].lower() in _NEEDS_A_NAME:
                raise PktError(f"`{words[0]}` needs {_NEEDS_A_NAME[words[0].lower()]}")
            if len(words) >= 3 and [w.lower() for w in words[:2]] == ["ip", "address"] and words[2] != "dhcp":
                if "/" in words[2]:
                    raise PktError(
                        f"IOS wants `ip address A MASK`, not {line.strip()!r}; "
                        f"or set the port's address: r['g0/0'].address = '{words[2]}'"
                    )
                if len(words) < 4:
                    raise PktError(f"{line.strip()!r} needs a mask: ip address A MASK")
                try:
                    ipaddress.IPv4Interface(f"{words[2]}/{words[3]}")
                except ValueError as e:
                    raise PktError(f"{line.strip()!r}: {e}") from None
            out.append(line)
    return out


def _vlan_list(spec: str) -> list[int]:
    """'10' / '10,20' / '10-12' -> [10] / [10, 20] / [10, 11, 12]."""
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        if not lo.isdigit() or (hi and not hi.isdigit()):
            raise PktError(f"bad VLAN list {spec!r}")
        a, b = int(lo), int(hi or lo)
        if a > b or not 1 <= a <= 4094 or not 1 <= b <= 4094:
            raise PktError(f"bad VLAN range {part!r}: VLANs run 1-4094")
        out.extend(range(a, b + 1))
    return out


_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


def _check_name(name: object) -> str:
    """A device name pktlib will write: letter first, then letters, digits, _ or -."""
    if not isinstance(name, str):
        raise TypeError(f"a device name is a string, got {type(name).__name__}")
    if not _NAME_RE.fullmatch(name):
        raise PktError(f"bad device name {name!r}: letter first, then up to 63 letters, digits, _ or -")
    return name


def _check_str(value: object, what: str) -> str:
    """A string pktlib will write into the file (ElementTree can't save anything else)."""
    if not isinstance(value, str):
        raise TypeError(f"{what} is a string, got {type(value).__name__}")
    if "\x00" in value:
        raise PktError(f"{what} can't hold a NUL character")
    return value


def _prefixlen(mask: str, where: str) -> int:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except ValueError:
        raise FileFormatError(f"{where} has mask {mask!r}, which isn't a netmask") from None


def _number(text: str, where: str) -> float:
    try:
        v = float(text)
    except ValueError:
        raise FileFormatError(f"{where} should be a number, got {text!r}") from None
    if not math.isfinite(v):
        raise FileFormatError(f"{where} should be a finite number, got {text!r}")
    return v


def _suggest(word: str, options: list[str]) -> str:
    """' (did you mean X?)' for a near miss, else ''."""
    close = difflib.get_close_matches(word, options, n=3, cutoff=0.6)
    return f" (did you mean {' or '.join(close)}?)" if close else ""


def _check_xy(at: object) -> tuple[float, float]:
    """A workspace position: two finite numbers."""
    if not isinstance(at, (tuple, list)) or len(at) != 2:
        raise TypeError(f"a position is (x, y), got {at!r}")
    for v in at:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"a position is two numbers, got {at!r}")
        if not math.isfinite(v):
            raise PktError(f"a position must be finite, got {at!r}")
    return float(at[0]), float(at[1])


Address = str | ipaddress.IPv4Interface  # '10.0.0.1/24', '10.0.0.1 255.255.255.0' or an IPv4Interface


def _interface(value: object) -> ipaddress.IPv4Interface:
    """An address with its mask, in any form people write one."""
    if isinstance(value, ipaddress.IPv4Interface):
        return value
    if not isinstance(value, str):
        raise TypeError(f"an address is 'a.b.c.d/len', 'a.b.c.d m.m.m.m' or an IPv4Interface, got {value!r}")
    text = value.strip()
    if ":" in text:
        raise PktError(f"{text!r}: IPv6 addresses aren't supported here yet")
    words = text.split()
    if len(words) == 2:
        text = "/".join(words)
    elif len(words) != 1 or "/" not in text:
        raise PktError(f"{value!r} needs a mask: '10.0.0.5/24' or '10.0.0.5 255.255.255.0'")
    try:
        return ipaddress.IPv4Interface(text)
    except ValueError as e:
        raise PktError(f"{value!r}: {e}") from None


def _gateway(gateway: object, iface: ipaddress.IPv4Interface | None) -> str:
    """A default gateway ('' for none), which must be inside the address's subnet."""
    if gateway is None or gateway == "":
        return ""
    if not isinstance(gateway, (str, ipaddress.IPv4Address)):
        raise TypeError(f"a gateway is an address like '10.0.0.1', got {gateway!r}")
    try:
        gw = ipaddress.IPv4Address(gateway)
    except ValueError:
        raise PktError(f"gateway {gateway!r} isn't an IPv4 address") from None
    if iface is not None and gw not in iface.network:
        raise PktError(f"gateway {gw} is outside {iface.network}")
    return str(gw)


# --- model ------------------------------------------------------------------


class Port:
    """One port on a device. Two Port objects for the same port are equal."""

    device: Device
    name: str
    el: ET.Element  # the PORT element: an escape hatch, not a stable API

    def __init__(self, device: Device, name: str, el: ET.Element) -> None:
        self.device, self.name, self.el = device, name, el

    def __repr__(self) -> str:
        return f"<Port {self.device.name}.{self.name}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Port) and other.el is self.el

    def __hash__(self) -> int:
        return id(self.el)

    @property
    def type(self) -> str:
        return _text(self.el, "TYPE")

    def _ios(self) -> tuple[str | None, str | None, bool] | None:
        if not self.device.has_ios:
            return None
        return interfaces(self.device.running_config).get(self.name, (None, None, False))

    @property
    def ip(self) -> str:
        """The address, or ''. IOS devices: read from the config (what Packet
        Tracer will run); PCs: the port's IP Configuration field."""
        ios = self._ios()
        return (ios[0] or "") if ios is not None else _text(self.el, "IP")

    @property
    def mask(self) -> str:
        ios = self._ios()
        return (ios[1] or "") if ios is not None else _text(self.el, "SUBNET")

    @property
    def up(self) -> bool:
        """IOS devices: not shut down. PCs: always on."""
        ios = self._ios()
        return ios[2] if ios is not None else True

    @property
    def mac(self) -> str:
        return _text(self.el, "MACADDRESS")

    @property
    def module(self) -> str | None:
        """The model of the removable card this port is on ('HWIC-2T',
        'PT-REPEATER-NM-1CGE'), or None for a built-in port."""
        for s in self.device.slots:
            if s.removable and s.module is not None and any(p is self.el for p in s.module.findall("PORT")):
                return s.model
        return None

    @property
    def address(self) -> str | None:
        """'a.b.c.d/len' or None."""
        if not self.ip or not self.mask:
            return None
        return f"{self.ip}/{_prefixlen(self.mask, f'{self.device.name}.{self.name}')}"

    @address.setter
    def address(self, value: Address) -> None:
        """'192.168.1.1/24', '192.168.1.1 255.255.255.0' or an IPv4Interface.
        On a router or switch this writes `interface X`, `ip address A M` and
        `no shutdown` into the config, as typing them would. On a PC it sets
        the port and keeps the gateway, which must still be in the subnet."""
        iface = _interface(value)
        if self.device.has_ios:
            self.device.config([f"interface {self.name}", f" ip address {iface.ip} {iface.netmask}", " no shutdown"])
            return
        gw = self.device.gateway
        if gw and ipaddress.IPv4Address(gw) not in iface.network:
            raise PktError(
                f"{self.device.name}'s gateway {gw} is outside {iface.network}: "
                f"set both with {self.device.name}.set_ip('{iface.with_prefixlen}', gateway=...)"
            )
        self.device.set_ip(iface, gw, port=self.name)

    @property
    def link(self) -> Link | None:
        """The cable in this port, or None."""
        return self.device.network.link_at(self.device, self.name)

    @property
    def peer(self) -> Port | None:
        """The port at the other end of this port's cable, or None."""
        link = self.link
        return None if link is None else link.other(self)

    # IOS settings of this interface, read from the running config
    def setting(self, command: str) -> str | None:
        """This interface's line for `command`, as written: setting('clock
        rate') -> 'clock rate 64000', or None. `command` is the line without
        its value."""
        return self.device.interface_config(self.name).get(command)

    def _switchport(self, *want: str) -> str | None:
        for line in self.device.interface_config(self.name).values():
            words = line.lower().split()
            if len(words) == len(want) + 1 and all(_abbrev(w, full) for w, full in zip(words, want, strict=False)):
                return line.split()[-1]
        return None

    @property
    def mode(self) -> str | None:
        """`switchport mode`: 'access', 'trunk', ... or None if not set."""
        return self._switchport("switchport", "mode")

    @property
    def access_vlan(self) -> int | None:
        """`switchport access vlan`, or None if not set (a switch port is then in VLAN 1)."""
        v = self._switchport("switchport", "access", "vlan")
        return int(v) if v is not None and v.isdigit() else None

    @property
    def voice_vlan(self) -> int | None:
        """`switchport voice vlan`, or None if not set."""
        v = self._switchport("switchport", "voice", "vlan")
        return int(v) if v is not None and v.isdigit() else None

    def connect(self, other: Port, cable: Cable | None = None) -> Link:
        """Cable this port to `other`. Serial: this end is the DCE (clock)."""
        if not isinstance(other, Port):
            raise TypeError(f"connect() wants a Port, got {type(other).__name__}")
        if other.device.network is not self.device.network:
            raise PktError("those ports are in different networks")
        return self.device.network.connect(self.device.name, self.name, other.device.name, other.name, cable)

    def disconnect(self) -> None:
        """Pull the cable out of this port."""
        self.device.network.disconnect(self.device.name, self.name)


class Device:
    """A device on the workspace. Iterating it gives its ports; `r1["g0/0"]`
    looks one up by name or IOS shorthand. Two Device objects for the same
    device are equal."""

    network: Network
    el: ET.Element  # the DEVICE element: an escape hatch, not a stable API

    def __init__(self, network: Network, el: ET.Element) -> None:
        self.network, self.el = network, el

    def __repr__(self) -> str:
        return f"<Device {self.name} {self.kind} {self.model}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Device) and other.el is self.el

    def __hash__(self) -> int:
        return id(self.el)

    def __iter__(self) -> Iterator[Port]:
        return iter(self.ports.values())

    def __len__(self) -> int:
        return len(self.ports)

    def __bool__(self) -> bool:
        return True  # a device is a thing first: one with no ports (Router-PT-Empty) is still there

    def __contains__(self, port: object) -> bool:
        """A Port of this device, or a port name ('fa0/1' works)."""
        if isinstance(port, Port):
            return port.device == self
        return port in self.ports

    @property
    def engine(self) -> ET.Element:
        return req(self.el, "ENGINE")

    @property
    def name(self) -> str:
        return _text(self.engine, "NAME")

    @name.setter
    def name(self, value: str) -> None:
        old = self.name
        if _check_name(value) == old:
            return
        if value in self.network:
            raise PktError(f"there is already a device called {value!r}")
        _set(self.engine, "NAME", value)
        node = self.network._physical_node(self.uuid)
        if node is not None:
            _set(node, "NAME", value)
        self.network._renamed(old, value)

    @property
    def kind(self) -> str:
        """'Router', 'Switch', 'Pc', ... as Packet Tracer names it."""
        return _text(self.engine, "TYPE")

    @property
    def model(self) -> str:
        return req(self.engine, "TYPE").get("model", "")

    @property
    def ref(self) -> str:
        """What a cable uses to point at this device: its SAVE_REF_ID, or in
        a pre-8 file (none), its position in the device list."""
        ref = _text(self.engine, "SAVE_REF_ID")
        if ref:
            return ref
        return str(list(self.network._devices_el).index(self.el))

    @property
    def uuid(self) -> str:
        return _text(self.el, "WORKSPACE/PHYSICAL").split(",")[-1]

    @property
    def xy(self) -> tuple[float, float]:
        return (
            _number(_text(self.el, "WORKSPACE/LOGICAL/X", "0"), f"{self.name}'s X"),
            _number(_text(self.el, "WORKSPACE/LOGICAL/Y", "0"), f"{self.name}'s Y"),
        )

    @xy.setter
    def xy(self, value: tuple[float, float]) -> None:
        x, y = _check_xy(value)
        _set(self.el, "WORKSPACE/LOGICAL/X", fmt_num(x))
        _set(self.el, "WORKSPACE/LOGICAL/Y", fmt_num(y))

    @property
    def dev_addr(self) -> str:
        return _text(self.el, "WORKSPACE/LOGICAL/DEV_ADDR")

    # ports
    def _port_elements(self) -> list[ET.Element]:
        return [p for p in self.engine.iter("PORT") if p.find("TYPE") is not None]

    @property
    def spec(self) -> dict[str, Any] | None:
        """This model's entry in pktlib's device spec, or None."""
        return SPEC.get(self.model)

    @property
    def ports(self) -> Ports:
        """Port name -> Port, read-only, in IOS order. Lookups take IOS
        shorthand too (`d.ports["fa0/1"]`). Names come from, in order of trust: the spec's
        names read off Packet Tracer's own menus; the IOS config (it lists
        interfaces in the order the file holds them, per type); otherwise
        type + running number."""
        els = self._port_elements()
        names_from_spec = (self.spec or {}).get("port_names")
        if names_from_spec and len(names_from_spec) == len(els):
            # None marks a port Packet Tracer keeps hidden (it never lists it)
            return Ports(self, {n: Port(self, n, el) for n, el in zip(names_from_spec, els, strict=True) if n})
        cfg_names = [line[len("interface ") :] for line in self.running_config if line.startswith("interface ")]
        by_prefix: dict[str, list[str]] = {}
        canon = []
        for n in cfg_names:
            try:
                canon.append(canonical_port(n))
            except PktError:
                continue
        for n in sorted(dict.fromkeys(canon), key=port_sort_key):  # each interface once, IOS order
            m = _PORT_RE.fullmatch(n)
            if m and m[3] is None:
                by_prefix.setdefault(m[1], []).append(n)
        # A Hub-PT names each port after its card's slot: with slot 2 empty Packet
        # Tracer 8.2 lists FastEthernet0, 1, 3, 4, 5 (hover table, 27 Oct 2026)
        slot_of = (
            {id(p): s.path[0] for s in self.slots if s.module is not None for p in s.module.iter("PORT")}
            if self.model in _SLOT_NAMED_MODELS
            else {}
        )
        out: dict[str, Port] = {}
        seen: dict[str, int] = {}
        for el in els:
            prefix = _PREFIX.get(_text(el, "TYPE"), _text(el, "TYPE").lstrip("e"))
            i = seen.get(prefix, 0)
            seen[prefix] = i + 1
            names = by_prefix.get(prefix)
            if id(el) in slot_of:
                name = f"{prefix}{slot_of[id(el)]}"
            else:
                name = names[i] if names and i < len(names) else f"{prefix}{i}"
            out[name] = Port(self, name, el)
        return Ports(self, {k: out[k] for k in sorted(out, key=port_sort_key)})

    def port(self, name: str) -> Port:
        """By name: exact ('Switch' on an IP phone), or IOS shorthand ('fa0/1')."""
        return self.ports[name]

    @property
    def interfaces(self) -> dict[str, Interface]:
        """IOS devices: every interface in the config, sub-interfaces and
        Vlan included -> Interface(address 'a.b.c.d/len' or None, up). Empty
        for PCs."""
        if not self.has_ios:
            return {}
        out = {}
        for name, (ip, mask, up) in interfaces(self.running_config).items():
            addr = f"{ip}/{_prefixlen(mask, f'{self.name} {name}')}" if ip and mask else None
            out[name] = Interface(addr, up)
        return out

    def interface_config(self, name: str) -> dict[str, str]:
        """An interface's settings other than its address and shutdown, after
        replaying the config. Keys are the command without its value:
        {'clock rate': 'clock rate 64000', 'switchport access vlan':
        'switchport access vlan 10', ...}. See also Port.setting()."""
        try:
            want = "interface " + canonical_port(name)
        except PktError:
            want = "interface " + name
        for header, body in blocks(self.running_config):
            if header == want:
                return interface_state(body)[3]
        return {}

    # hardware
    @property
    def slots(self) -> list[Slot]:
        """Every slot in the device, fitted or empty, built-in ones included."""
        root = self.engine.find("MODULE")
        return [] if root is None else slots(root)

    @property
    def modules(self) -> list[str]:
        """Models of the removable modules fitted, e.g. ['WIC-2T', 'AC-POWER-SUPPLY']."""
        return [s.model for s in self.slots if s.removable and s.model is not None]

    def free_slots(self, slot_type: str | None = None) -> list[Slot]:
        """Empty removable slots, of one type ('eInterfaceCard', ...) or all."""
        return [s for s in self.slots if s.removable and s.empty and (slot_type is None or s.type == slot_type)]

    def add_module(self, model: str, slot: tuple[int, ...] | None = None) -> Slot:
        """Fit a module ('WIC-2T', 'AC-POWER-SUPPLY', ...; see
        pktlib.module_models()) into the first free slot that takes it, or into
        `slot` (a Slot.path). Refuses a full or wrong-type slot, so a device
        never gets more of anything than it has room for. New router ports get
        their IOS names and a factory-default block in the config."""
        _check_str(model, "a module model")
        if slot is not None and (
            not isinstance(slot, (tuple, list)) or not all(isinstance(i, int) and not isinstance(i, bool) for i in slot)
        ):
            raise TypeError(f"a slot is a tuple of ints like (0, 1) (see d.free_slots()), got {slot!r}")
        accepts = (self.spec or {}).get("accepts")
        known = module_models()
        if model not in known:
            if accepts and model in accepts:
                raise PktError(
                    f"Packet Tracer fits {model} in a {self.model}, but pktlib has no template for {model} yet"
                )
            raise NotFound(
                f"unknown module {model!r}" + _suggest(model, accepts or known) + "; pktlib.module_models() lists them"
            )
        if accepts is not None and model not in accepts:
            raise PktError(
                f"a {self.model} doesn't take {model} in Packet Tracer"
                + (f" (it takes: {', '.join(accepts)})" if accepts else " (it has no swappable modules)")
            )
        slot_type, mod = fresh_module(model)
        if slot is None:
            free = self.free_slots(slot_type)
            if not free:
                have = [s for s in self.slots if s.type == slot_type]
                where = SLOT_WORDS.get(slot_type, slot_type)
                raise PktError(
                    f"{self.name} has no free {where} for {model}"
                    + (f" (all {len(have)} in use)" if have else f" ({self.model} has none)")
                )
            target = free[0]
        else:
            found = next((s for s in self.slots if s.path == tuple(slot)), None)
            if found is None:
                raise NotFound(f"{self.name} has no slot {slot}")
            target = found
            if not target.removable:
                raise PktError(f"slot {slot} on {self.name} is built in")
            if target.type != slot_type:
                raise PktError(
                    f"{model} needs a {SLOT_WORDS.get(slot_type, slot_type)}; slot {slot} is a "
                    f"{SLOT_WORDS.get(target.type, target.type)}"
                )
            if not target.empty:
                raise PktError(f"slot {slot} on {self.name} already holds {target.model}")
        rng, taken = self.network._rng, self.network._taken()
        for el in mod.iter():
            if el.text and _MAC_RE.fullmatch(el.text.strip()):
                el.text = _unique(lambda: _rand_mac(rng), taken)
        _refresh_link_locals(mod)
        target.el.append(mod)
        new_ports = port_names_for(mod, target.path, self.model)
        if self.has_ios and new_ports:
            block = []
            for _, name in new_ports:
                if model in _SWITCH_MODULES:  # switch ports: up, no address, as PT writes its own
                    block += [f"interface {name}", "!"]
                    continue
                block += [f"interface {name}", " no ip address"]
                if is_serial(name):
                    block.append(" clock rate 2000000")
                block += [" shutdown", "!"]
            self.config(block, check_ports=False)  # the new ports aren't named until this config
        return target

    def remove_module(self, slot: tuple[int, ...]) -> str:
        """Take out the module in `slot`; returns its model. Refuses built-in
        hardware and modules with cables still plugged into them."""
        if not isinstance(slot, (tuple, list)) or not all(isinstance(i, int) and not isinstance(i, bool) for i in slot):
            raise TypeError(f"a slot is a tuple of ints like (0, 1) (see d.slots), got {slot!r}")
        target = next((s for s in self.slots if s.path == tuple(slot)), None)
        mod = None if target is None else target.module
        if target is None or mod is None:
            raise NotFound(f"{self.name} has nothing in slot {slot}")
        if not target.removable:
            raise PktError(f"slot {slot} on {self.name} is built in")
        names = {name for _, name in port_names_for(mod, target.path, self.model)}
        mod_ports = {id(p) for p in mod.iter("PORT")}
        for p in self.ports.values():
            if id(p.el) in mod_ports and p.link is not None:
                raise PktError(f"unplug {self.name}.{p.name} before removing {target.model}")
        model = mod.findtext("MODEL") or ""
        # cabled ports must keep their names, or their cables would point at nothing
        before = {id(p.el): p.name for p in self if id(p.el) not in mod_ports and p.link is not None}
        index = list(target.el).index(mod)
        old_config = self.running_config if self.has_ios else None
        target.el.remove(mod)
        if self.has_ios and names:
            keep, skip = [], False
            for line in self.running_config:
                if line.startswith("interface "):
                    try:
                        skip = canonical_port(line.split(None, 1)[1]) in names
                    except PktError:
                        skip = False
                elif not line.startswith(" ") and line != "!":
                    skip = False
                if not skip:
                    keep.append(line)
            self.running_config = keep
        shifted = [f"{before[id(p.el)]} -> {p.name}" for p in self if before.get(id(p.el), p.name) != p.name]
        if shifted:
            # a device whose names count ports (no IOS, no slot naming) would
            # renumber the rest; Hub-PT and Switch-PT name by slot, so they never get here
            target.el.insert(index, mod)
            if old_config is not None:
                self.running_config = old_config
            raise PktError(
                f"taking {model} out of {self.name} would rename its cabled ports ({', '.join(shifted[:3])}); "
                f"unplug them first: pktlib doesn't know Packet Tracer's names for that yet"
            )
        return model

    def __getitem__(self, name: str) -> Port:
        """`r1["fa0/0"]` is `r1.port("fa0/0")`."""
        return self.port(name)

    # config
    def _config(self, tag: str) -> list[str]:
        el = self.engine.find(tag)
        return [] if el is None else [item.text or "" for item in el]

    def _set_config(self, tag: str, lines: list[str]) -> None:
        el = self.engine.find(tag)
        if el is None:
            raise PktError(f"{self.name} ({self.kind}) has no IOS config")
        for c in list(el):
            el.remove(c)
        for line in lines:
            ET.SubElement(el, "LINE").text = line

    @property
    def has_ios(self) -> bool:
        return self.engine.find("RUNNINGCONFIG") is not None

    @property
    def running_config(self) -> list[str]:
        return self._config("RUNNINGCONFIG")

    @running_config.setter
    def running_config(self, lines: list[str]) -> None:
        """Packet Tracer replays this text as IOS commands when it opens the
        file, so plain config commands (abbreviations included) work. The
        startup config gets the same lines."""
        self._set_config("RUNNINGCONFIG", list(lines))
        self._set_config("STARTUPCONFIG", list(lines))
        # A switch keeps its startup config in flash as config.text, and Packet
        # Tracer boots it from there when the file is there, ignoring the two
        # above (a lecturer's switches saved with `write mem` came back with
        # their old banner and passwords). Keep it in step, as `write mem` would.
        for f in self.engine.iter("FILE"):
            cfg = f.find("FILE_CONTENT/CONFIG")
            if f.findtext("NAME") == "config.text" and cfg is not None:
                for c in list(cfg):
                    cfg.remove(c)
                for line in lines:
                    ET.SubElement(cfg, "LINE").text = line

    def config(self, commands: str | Iterable[str], *, check_ports: bool = True) -> Device:
        """Add IOS config-mode commands, as if typed after `configure terminal`:
        one string of lines (indented however you like, as long as block
        bodies are indented more than their headers) or a list of lines.
        Returns the device, so calls chain.

        Switches keep VLANs in a VLAN database, not the running config (like
        vlan.dat on a real switch), and Packet Tracer doesn't rebuild it from
        the text. So on a switch, `vlan N` / ` name X` blocks go into the
        database, and `switchport access vlan N` creates VLAN N if it's
        missing, as real IOS does; `no vlan N` takes it out.

        Lines are written as IOS saves them: tabs count as one space of
        indent, and mode changes (`exit`, `end`, `configure terminal`) are
        left out, since a saved config has none and Packet Tracer replays the
        file top to bottom. Config Packet Tracer is known to drop on load
        raises a PktWarning (see iosconfig.refused).

        `interface X` for a physical port the device doesn't have is refused,
        as IOS refuses it: names of ports on models without a checked name
        list come from the config, so a stray one would rename the real ports.
        check_ports=False skips that (for ports a module is adding)."""
        if self.kind in GUI_ONLY_KINDS:
            raise PktError(
                f"{self.name} is a {self.model}: Packet Tracer sets it up in its GUI and ignores IOS "
                f"text in the file, so pktlib can't configure it yet"
            )
        if isinstance(commands, str):
            lines = textwrap.dedent(commands.expandtabs(1)).strip("\n").splitlines()
            first = next((line for line in lines if line.strip()), "")
            if first.startswith(" "):
                raise PktError(
                    f"config text starts indented ({first.strip()!r}) but a later line isn't: indent block bodies only"
                )
            commands = lines
        if self.kind == "IpPhone":
            # check 11, 2026-10-26: a 7960's `hostname` was gone from Packet Tracer's re-save
            raise PktError(f"{self.name} is a {self.model}: it has no CLI, and Packet Tracer drops config in the file")
        commands = _expand_interface_ranges(_prepare_commands(commands))
        if check_ports:
            self._check_interfaces(commands)
        add: list[tuple[int, str | None]] = []
        remove: list[int] = []
        if self.engine.find("VLANS") is not None and (
            self.kind in SWITCH_KINDS or any(m in _SWITCH_MODULES for m in self.modules)
        ):
            # switches, and routers with an EtherSwitch card
            commands, add, remove = self._plan_vlans(commands)
        for line, why in refused(commands, self.model):
            warnings.warn(f"{self.name}: `{line.strip()}` {why}", PktWarning, stacklevel=3)
        merged = merge_config(self.running_config, commands)
        # everything is checked; now change the device
        for v in remove:
            if v in self.vlans:
                self.remove_vlan(v)
        for v, name in add:
            self.add_vlan(v, name)
        self.running_config = merged
        return self

    def _check_interfaces(self, commands: list[str]) -> None:
        """Refuse `interface X` (or a sub-interface X.N) for a physical port this device doesn't have."""
        ports = self.ports
        known = set(ports) | {line.split(None, 1)[1] for line in self.running_config if line.startswith("interface ")}
        for c in commands:
            words = c.split()
            if c.startswith(" ") or not words or words[0].lower() != "interface":
                continue
            try:
                name = canonical_port(" ".join(words[1:]))
            except PktError:
                continue  # not a port name pktlib knows: left to IOS
            m = _PORT_RE.fullmatch(name)
            if m is None or m[1] not in _PHYSICAL:
                continue  # Loopback, Vlan, Tunnel, Port-channel: config makes those
            port = f"{m[1]}{m[2]}"
            if port not in known:
                what = name if port == name else f"{port} (for {name})"
                raise PktError(f"{self.name} has no interface {what}; it has {', '.join(ports) or 'none'}")

    def _plan_vlans(self, commands: list[str]) -> tuple[list[str], list[tuple[int, str | None]], list[int]]:
        """Split VLAN database commands out of `commands` without changing
        anything: (the rest, VLANs to add or name, VLANs to remove)."""
        out: list[str] = []
        add: list[tuple[int, str | None]] = []
        remove: list[int] = []
        current: list[int] = []
        known = set(self.vlans)
        for c in commands:
            words = c.split()
            low = [w.lower() for w in words]
            if not c.startswith(" ") and len(words) == 2 and low[0] == "vlan":
                current = _vlan_list(words[1])
                add += [(v, None) for v in current]
                known.update(current)
                continue
            if not c.startswith(" ") and len(words) == 3 and low[:2] == ["no", "vlan"]:
                current = []
                for v in _vlan_list(words[2]):
                    if v == 1 or 1002 <= v <= 1005:
                        raise PktError(f"VLAN {v} is a default VLAN and can't be removed")
                    remove.append(v)
                    known.discard(v)
                continue
            if current and c.startswith(" "):
                if low[0] == "name" and len(words) >= 2:
                    add += [(v, " ".join(words[1:])) for v in current]
                continue
            current = []
            # an access or voice VLAN that doesn't exist yet is created, as IOS does
            # (a missing voice VLAN left 24 phones unregistered; found by the stress tests)
            if (
                len(words) == 4
                and _abbrev(low[0], "switchport")
                and (_abbrev(low[1], "access") or _abbrev(low[1], "voice"))
                and _abbrev(low[2], "vlan")
                and words[3].isdigit()
            ):
                v = int(words[3])
                if not 1 <= v <= 4094:
                    raise PktError(f"VLAN numbers run 1-4094, got {v}")
                if v not in known:
                    add.append((v, None))
                    known.add(v)
            out.append(c)
        names = {v: n for v, n in self.vlans.items() if v not in remove}
        for v, name in add:
            if name is not None:
                _check_vlan_name(self, v, name, names)
                names[v] = name
        return out, add, remove

    # VLAN database (switches)
    @property
    def vlans(self) -> Mapping[int, str]:
        """VLAN number -> name, read-only; change it with add_vlan()/remove_vlan()."""
        el = self.engine.find("VLANS")
        found = {} if el is None else {req_int_attr(v, "number"): v.get("name", "") for v in el.findall("VLAN")}
        return MappingProxyType(found)

    def add_vlan(self, number: int, name: str | None = None) -> None:
        """Create VLAN `number` (or rename it). Name defaults to VLAN0010 style."""
        if isinstance(number, bool) or not isinstance(number, int):
            raise TypeError(f"a VLAN number is an int, got {number!r}")
        if not 1 <= number <= 4094:
            raise PktError(f"VLAN numbers run 1-4094, got {number}")
        if name is not None:
            _check_str(name, "a VLAN name")
        el = self.engine.find("VLANS")
        if el is None:
            raise PktError(f"{self.name} ({self.kind}) has no VLAN database")
        if name is not None:
            _check_vlan_name(self, number, name, self.vlans)
        for v in el.findall("VLAN"):
            if req_int_attr(v, "number") == number:
                if name is not None:
                    v.set("name", name)
                return
        new = ET.Element("VLAN", number=str(number), rspan="0", name=name or f"VLAN{number:04d}")
        # keep the database in number order, like `show vlan`
        idx = sum(1 for v in el.findall("VLAN") if req_int_attr(v, "number") < number)
        el.insert(idx, new)

    def remove_vlan(self, number: int) -> None:
        """Delete VLAN `number` from the database. Ports still in it are left
        as they are, as on IOS (they go inactive), with a PktWarning."""
        if isinstance(number, bool) or not isinstance(number, int):
            raise TypeError(f"a VLAN number is an int, got {number!r}")
        if number == 1 or 1002 <= number <= 1005:
            raise PktError(f"VLAN {number} is a default VLAN and can't be removed")
        el = self.engine.find("VLANS")
        if el is not None:
            for v in el.findall("VLAN"):
                if req_int_attr(v, "number") == number:
                    el.remove(v)
                    users = [
                        h.split(None, 1)[1]
                        for h, body in blocks(self.running_config)
                        if h.startswith("interface ")
                        and any(re.fullmatch(rf"switchport (access|voice) vlan {number}", b) for b in body)
                    ]
                    if users:
                        warnings.warn(
                            f"{self.name}: VLAN {number} removed while {', '.join(users)} still use it",
                            PktWarning,
                            stacklevel=2,
                        )
                    return
        raise NotFound(f"{self.name} has no VLAN {number}")

    # licences (ISR technology packages)
    @property
    def licenses(self) -> Mapping[str, str]:
        """Feature -> state, as `show license` puts it: {'securityk9':
        'Inactive', 'ipbasek9': 'Active, In Use', ...}. Empty if the model
        has no licence manager."""
        return MappingProxyType(
            {
                feature: lic.findtext("LICENSE_STATE") or ""
                for lic in self.engine.iter("LICENSE")
                if (feature := lic.findtext("FEATURE_NAME"))
            }
        )

    def enable_license(self, feature: str = "securityk9") -> None:
        """Turn a technology package on as if `license boot module ...
        technology-package <feature>` had been entered, the EULA accepted and
        the router reloaded. Copied from what Packet Tracer 8.2 saved after
        exactly that on a 2901 (25 Oct 2026): the feature's CURRENT_BOOT and
        NEXT_REBOOT go to 2, its state to "Active, In Use", and the config
        gains the `license boot` line."""
        lic = next((lic for lic in self.engine.iter("LICENSE") if lic.findtext("FEATURE_NAME") == feature), None)
        if lic is None:
            raise NotFound(
                f"{self.name} ({self.model}) has no {feature} licence (it has {', '.join(self.licenses) or 'none'})"
            )
        module = _LICENSE_MODULE.get(self.model)
        if module is None:
            raise PktError(f"pktlib doesn't know the licence module name for a {self.model} yet")
        for tag, val in (("CURRENT_BOOT", "2"), ("NEXT_REBOOT", "2"), ("LICENSE_STATE", "Active, In Use")):
            el = lic.find(tag)
            if el is None:
                el = ET.SubElement(lic, tag)
            el.text = val
        # The CLI command set is what actually lets the commands in: with the
        # licence active but the set left at 2900_universal_base_15.1, Packet
        # Tracer dropped every `crypto` line on load; PT's own save says
        # 2900_universal_security_15.1.
        cmd = self.engine.find("CURRENT_COMMAND_SET")
        token = _LICENSE_COMMAND_SET.get(feature)
        if cmd is not None and token and cmd.text:
            cmd.text = re.sub(r"_base_", f"_{token}_", cmd.text)
        line = f"license boot module {module} technology-package {feature}"
        rc = self.running_config
        if line not in rc:  # where Packet Tracer saves it: after `license udi`
            at = next((i + 1 for i, line in enumerate(rc) if line.startswith("license udi ")), None)
            if at is None:
                self.config([line])
            else:
                self.running_config = rc[:at] + [line] + rc[at:]

    def generate_rsa_key(self, bits: int = 1024) -> None:
        """What `crypto key generate rsa` with `bits` does, for SSH. The key
        isn't in the config: Packet Tracer 8.2 keeps it in ENGINE/SECURITY
        (seen 26 Oct 2026 on a 2901), named hostname.domain, as rows of
        15-bit random words. It's a stand-in, not a real RSA key, so random
        words of the same shape are as good as Packet Tracer's own. Needs a
        hostname and `ip domain-name`, as on the CLI."""
        if isinstance(bits, bool) or not isinstance(bits, int):
            raise TypeError(f"bits is an int, got {bits!r}")
        if not 360 <= bits <= 2048:
            raise PktError(f"modulus must be 360 to 2048 bits, not {bits}")
        sec = self.engine.find("SECURITY")
        if sec is None:
            raise PktError(f"{self.name} ({self.model}) has no SECURITY section, so no SSH")
        domain = next((line.split()[-1] for line in self.running_config if line.startswith("ip domain-name ")), None)
        if domain is None:
            raise PktError(f"{self.name} needs `ip domain-name` before an RSA key can be made")
        rng = self.network._rng

        def key() -> str:
            words = [f"{rng.getrandbits(15):08x}" for _ in range(23)]
            rows = [" " + "  ".join(words[i : i + 8]) for i in range(0, 23, 8)]
            return "\n".join(rows) + f"  {rng.getrandbits(15):x}"

        name = f"{self.hostname}.{domain}"
        for tag, val in (
            ("KEY_NAME", name),
            ("TEMP_KEY_NAME", name + ".server"),
            ("RSA_KEY", key()),
            ("TEMP_RSA_KEY", key()),
            ("TIME_DATE", "0:0:30 UTC March 1 1993"),
            ("ENABLED", "1"),
            ("MODULUS_BITS", str(bits)),
        ):
            el = sec.find(tag)
            if el is None:
                el = ET.SubElement(sec, tag)
            el.text = val

    @property
    def rsa_key(self) -> RsaKey | None:
        """RsaKey(name, bits) if the device has an RSA key, else None."""
        sec = self.engine.find("SECURITY")
        if sec is None or sec.findtext("ENABLED") != "1":
            return None
        return RsaKey(sec.findtext("KEY_NAME") or "", int(_number(sec.findtext("MODULUS_BITS") or "0", "MODULUS_BITS")))

    # the network around it
    @property
    def links(self) -> list[Link]:
        """The cables plugged into this device."""
        return [link for link in self.network.links if self in (link.ports[0].device, link.ports[1].device)]

    @property
    def neighbors(self) -> list[Device]:
        """The devices cabled to this one, each once, in cable order."""
        out = []
        for link in self.links:
            for p in link.ports:
                if p.device != self and p.device not in out:
                    out.append(p.device)
        return out

    @property
    def hostname(self) -> str:
        for line in self.running_config:
            if line.startswith("hostname "):
                return line.split(None, 1)[1]
        return _text(self.engine, "SYS_NAME")

    # end devices
    def _end_port(self, port: str | None) -> Port:
        if self.kind in GUI_ONLY_KINDS:
            raise PktError(
                f"{self.name} is a {self.model}: Packet Tracer sets its addresses in its GUI, so pktlib can't yet"
            )
        if self.has_ios:
            raise PktError(f"{self.name} runs IOS: set r['g0/0'].address, or config('interface X\\n ip address dhcp')")
        if port is None and not len(self):
            raise PktError(f"{self.name} ({self.model}) has no ports to give an address")
        p = self.port(port) if port is not None else next(iter(self.ports.values()))
        if p.el.find("IP") is None or p.el.find("SUBNET") is None:
            raise PktError(f"{self.name}.{p.name} has no IP settings in Packet Tracer")
        return p

    @property
    def gateway(self) -> str:
        """An end device's default gateway ('' for none). Settable; it must be
        inside the subnet of the device's address."""
        return _text(self.engine, "GATEWAY")

    @gateway.setter
    def gateway(self, value: str) -> None:
        p = self._end_port(None)
        gw = _gateway(value, _interface(p.address) if p.address else None)
        if p.el.find("PORT_GATEWAY") is not None:
            _set(p.el, "PORT_GATEWAY", gw)
        if self.engine.find("GATEWAY") is not None:
            _set(self.engine, "GATEWAY", gw)

    def use_dhcp(self, port: str | None = None) -> None:
        """End devices: take the address from a DHCP server (IP Configuration
        > DHCP in Packet Tracer). Packet Tracer asks for a lease when it
        opens the file. `d.dhcp = True` does the same for the first port."""
        p = self._end_port(port)
        if p.el.find("PORT_DHCP_ENABLE") is None:
            raise PktError(f"{self.name}.{p.name} can't do DHCP")
        _set(p.el, "PORT_DHCP_ENABLE", "true")
        for tag in ("IP", "SUBNET", "PORT_GATEWAY"):
            if p.el.find(tag) is not None:
                _set(p.el, tag, "")
        if self.engine.find("GATEWAY") is not None:
            _set(self.engine, "GATEWAY", "")

    @property
    def dhcp(self) -> bool:
        """True if any port takes its address from DHCP. Settable: True is
        use_dhcp(), False turns DHCP off (static, no address until set_ip)."""
        return any(_text(p.el, "PORT_DHCP_ENABLE") == "true" for p in self.ports.values())

    @dhcp.setter
    def dhcp(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError(f"dhcp is True or False, got {value!r}")
        if value:
            self.use_dhcp()
            return
        self._end_port(None)
        for p in self.ports.values():
            if _text(p.el, "PORT_DHCP_ENABLE") == "true":
                _set(p.el, "PORT_DHCP_ENABLE", "false")

    def set_ip(self, address: Address, gateway: str = "", *, port: str | None = None) -> None:
        """Give an end device a static address, as IP Configuration > Static
        does: set_ip('10.0.0.5/24', '10.0.0.1'). The address can also be
        '10.0.0.5 255.255.255.0' or an IPv4Interface. DHCP goes off.
        Routers and switches: set r['g0/0'].address instead."""
        iface = _interface(address)
        gw = _gateway(gateway, iface)
        p = self._end_port(port)
        if p.type == "eBluetooth":
            # check 14, 2026-10-26: IP Configuration offers no Bluetooth, and Config > Bluetooth has no IP fields
            raise PktError(f"{self.name}.{p.name}: Packet Tracer has no IP settings for Bluetooth")
        _set(p.el, "IP", str(iface.ip))
        _set(p.el, "SUBNET", str(iface.netmask))
        if p.el.find("PORT_GATEWAY") is not None:
            _set(p.el, "PORT_GATEWAY", gw)
        if p.el.find("PORT_DHCP_ENABLE") is not None:
            _set(p.el, "PORT_DHCP_ENABLE", "false")  # a static address turns DHCP off, as the GUI does
        g = self.engine.find("GATEWAY")
        if g is not None:
            g.text = gw


def _check_vlan_name(dev: Device, number: int, name: str, names: Mapping[int, str]) -> None:
    """Check 3, 2026-10-26: a second VLAN named like one already there was
    gone from Packet Tracer's re-save (VLAN 60 'SAME' beside VLAN 50 'SAME')."""
    for v, n in names.items():
        if v != number and n == name:
            raise PktError(f"{dev.name}: VLAN {v} is already named {name!r}, and Packet Tracer drops a second one")


class Link:
    """A cable. Two Link objects for the same cable are equal."""

    network: Network
    el: ET.Element  # the LINK element: an escape hatch, not a stable API

    def __init__(self, network: Network, el: ET.Element) -> None:
        self.network, self.el = network, el

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Link) and other.el is self.el

    def __hash__(self) -> int:
        return id(self.el)

    def __repr__(self) -> str:
        (a, ap), (b, bp) = self.ends
        return f"<Link {a}.{ap} {self.cable} {b}.{bp}>"

    @property
    def medium(self) -> str:
        return _text(self.el, "TYPE")

    @property
    def cable(self) -> str:
        """'straight', 'cross', 'serial', 'coax' or 'phone'."""
        if self.medium in _MEDIUM_CABLE:
            return _MEDIUM_CABLE[self.medium]
        t = _text(self.el, "CABLE/TYPE")
        return {"eStraightThrough": "straight", "eCrossOver": "cross"}.get(t, t)

    @property
    def ends(self) -> tuple[End, End]:
        """The two ends as names, End(device, port): handy to print or compare.
        A device the file doesn't have reads as '?'. See `ports` for objects."""
        cable = req(self.el, "CABLE")
        ports = [p.text or "" for p in cable.findall("PORT")]
        if len(ports) != 2:
            raise FileFormatError(f"a cable should name 2 ports, this one names {len(ports)}")
        a = self.network._by_ref(_text(cable, "FROM"))
        b = self.network._by_ref(_text(cable, "TO"))
        return End(a.name if a is not None else "?", ports[0]), End(b.name if b is not None else "?", ports[1])

    @property
    def ports(self) -> tuple[Port, Port]:
        """The two ports this cable joins."""
        found = []
        for device, port in self.ends:
            if device == "?":
                raise FileFormatError(f"a cable points at a device that isn't in the file ({self})")
            found.append(self.network.device(device).port(port))
        return found[0], found[1]

    def other(self, port: Port) -> Port:
        """The far end from `port`."""
        a, b = self.ports
        if port == a:
            return b
        if port == b:
            return a
        raise PktError(f"{port.device.name}.{port.name} isn't on this cable ({self})")

    @property
    def dce(self) -> End | None:
        """The DCE end of a serial cable, End(device, port), or None."""
        ref = _text(self.el, "CABLE/DCEDEV")
        if not ref:
            return None
        d = self.network._by_ref(ref)
        return End(d.name if d is not None else "?", _text(self.el, "CABLE/DCEPORT"))


class End(NamedTuple):
    """One end of a cable, by name."""

    device: str
    port: str


class Interface(NamedTuple):
    """An IOS interface as configured: address 'a.b.c.d/len' (or None), and up."""

    address: str | None
    up: bool


class RsaKey(NamedTuple):
    """A device's SSH key: its name (hostname.domain) and modulus bits."""

    name: str
    bits: int


class Pdu(NamedTuple):
    """A Simple PDU (ping check) under the workspace."""

    scenario: str
    source: str
    destination: str
    ip: str


class Profile(NamedTuple):
    """Options > User Profile in Packet Tracer."""

    name: str
    email: str = ""
    info: str = ""


class Ports(Mapping[str, Port]):
    """A device's ports by name, read-only and in IOS order. Lookups take
    Packet Tracer's own names ('Switch' on an IP phone, case aside) or IOS
    shorthand ('fa0/1'); a missing port is a NotFound (a KeyError)."""

    _device: Device
    _ports: dict[str, Port]

    def __init__(self, device: Device, ports: dict[str, Port]) -> None:
        self._device, self._ports = device, ports

    def __getitem__(self, name: str) -> Port:
        if not isinstance(name, str):
            raise TypeError(f"a port name is a string, got {type(name).__name__}")
        if name in self._ports:
            return self._ports[name]
        for real, port in self._ports.items():
            if real.lower() == name.strip().lower():
                return port
        try:
            want = canonical_port(name)
        except PktError:
            raise NotFound(f"{self._device.name} has no port {name!r} (has {', '.join(self._ports)})") from None
        if want not in self._ports:
            raise NotFound(f"{self._device.name} has no port {want} (has {', '.join(self._ports)})")
        return self._ports[want]

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        try:
            self[name]
        except PktError:  # NotFound, or not a port name at all
            return False
        return True

    def __iter__(self) -> Iterator[str]:
        return iter(self._ports)

    def __len__(self) -> int:
        return len(self._ports)

    def __repr__(self) -> str:
        return f"<Ports of {self._device.name}: {', '.join(self._ports)}>"


SPEC: dict[str, dict[str, Any]] = json.loads(
    resources.files("pktlib").joinpath("spec").joinpath("devices.json").read_text("utf-8")
)
SWITCH_KINDS = {"Switch", "MultiLayerSwitch", "Hub", "Repeater", "Bridge"}
# the module name in `license boot module <name> technology-package ...`; only
# the 2901's (c2900) has been seen working in Packet Tracer
_LICENSE_MODULE = {"2901": "c2900"}
_LICENSE_COMMAND_SET = {"securityk9": "security"}  # feature -> its CURRENT_COMMAND_SET word
# Configured through Packet Tracer's GUI pages; IOS text in the file is ignored
GUI_ONLY_KINDS = {"WirelessRouter", "WirelessRouterNewGeneration", "HomeGateway", "CentralOfficeServer"}
_SWITCH_MODULES = {"HWIC-4ESW", "NM-ESW-161", "NIM-ES2-4"}  # EtherSwitch cards: their ports are switch ports
_SLOT_NAMED_MODELS = {"Hub-PT"}  # no IOS; each port is named after its card's slot
# cables as Packet Tracer 8.2 writes them (coax and phone copied from links drawn in the GUI)
Cable = Literal["straight", "cross", "serial", "coax", "phone"]
_CABLES: tuple[Cable, ...] = get_args(Cable)
_CABLE_MEDIUM: dict[Cable, str] = {
    "straight": "eCopper",
    "cross": "eCopper",
    "serial": "eSerial",
    "coax": "eCoaxial",
    "phone": "ePhoneLine",
}
_MEDIUM_CABLE = {"eSerial": "serial", "eCoaxial": "coax", "ePhoneLine": "phone"}
_CABLE_COLOUR: dict[Cable, str] = {
    "straight": "#6ba72e",
    "cross": "#6ba72e",
    "serial": "#1e59a5",
    "coax": "#747578",
    "phone": "#f3acd3",
}
_PORT_CABLE: dict[str, Cable] = {"eCopperCoaxial": "coax", "eModem": "phone"}  # ports that take only that cable
# Seen in Packet Tracer 8.2 on 25 Oct 2026, each cabled to a PC both ways: these
# FastEthernet ports only come up on a straight cable, as a switch port does.
# (Access points and the central office server's Backbone come up on a
# cross-over, like a host. Gigabit ports came up on either.)
_SWITCH_LIKE_KINDS = SWITCH_KINDS | {"Sniffer", "CableModem", "DslModem", "Cloud"}
# interface types that are ports on the device; the rest (Loopback, Vlan, Tunnel, ...) are made by config
_PHYSICAL = set(_PREFIX.values())
_HOME_ROUTER_KINDS = {"WirelessRouter", "WirelessRouterNewGeneration", "HomeGateway"}


def _switch_like(port: Port) -> bool:
    if port.device.model == "AccessPoint-PT-AC":
        return True  # unlike the other APs, it links to a PC on straight (seen 25 Oct)
    kind = port.device.kind
    if kind in _HOME_ROUTER_KINDS:
        return port.name != "Internet"  # LAN ports are a built-in switch
    return kind in _SWITCH_LIKE_KINDS


ALIASES = {
    "2960": "2960-24TT",
    "3560": "3560-24PS",
    "3650": "3650-24PS",
    "4331": "ISR4331",
    "4321": "ISR4321",
    "pc": "PC-PT",
    "laptop": "Laptop-PT",
    "server": "Server-PT",
    "printer": "Printer-PT",
}


def models(*, verified_only: bool = True) -> list[str]:
    """Device models pktlib can create (all it knows about with verified_only=False)."""
    return sorted(m for m, s in SPEC.items() if s["verified"] or not verified_only)


def _template(key: str) -> ET.Element:
    raw = resources.files("pktlib").joinpath("data").joinpath(f"{key}.xml.gz").read_bytes()
    return ET.fromstring(gzip.decompress(raw))


def _default_router_config(hostname: str, ports: list[str]) -> list[str]:
    lines = [
        "!",
        "version 12.4",
        "no service timestamps log datetime msec",
        "no service timestamps debug datetime msec",
        "no service password-encryption",
        "!",
        f"hostname {hostname}",
        "!",
        "no ip cef",
        "no ipv6 cef",
        "!",
        "spanning-tree mode pvst",
        "!",
    ]
    for p in ports:
        lines.append(f"interface {p}")
        lines.append(" no ip address")
        if p.startswith(("FastEthernet", "GigabitEthernet", "Ethernet")):
            lines += [" duplex auto", " speed auto"]
        if is_serial(p):
            lines.append(" clock rate 2000000")
        lines += [" shutdown", "!"]
    lines += [
        "interface Vlan1",
        " no ip address",
        " shutdown",
        "!",
        "ip classless",
        "!",
        "ip flow-export version 9",
        "!",
        "line con 0",
        "!",
        "line aux 0",
        "!",
        "line vty 0 4",
        " login",
        "!",
        "end",
    ]
    return lines


class Network:
    """A Packet Tracer file as objects. `load()` / `new()` / `save()`.

    Iterating it gives its devices; `net["R1"]` looks one up by name, and
    `"R1" in net` / `r1 in net` test membership."""

    def __init__(self, root: ET.Element, *, seed: int | None = None, strict: bool = True) -> None:
        """strict (the default): refuse a file from a Packet Tracer newer than
        any edition pktlib knows, or with a version stamp that isn't one, as
        Packet Tracer itself would. strict=False reads it anyway."""
        if root.tag != "PACKETTRACER5":
            raise FileFormatError(f"not Packet Tracer XML (root is <{root.tag}>)")
        self.root: ET.Element = root  # PACKETTRACER5: an escape hatch, not a stable API
        self._rng = random.Random(seed)
        self._strict = strict
        self._level = 9  # zlib level to save at: Packet Tracer's, or what the loaded file used
        self._upgrade_refs()
        if strict:
            version = _text(root, "VERSION")
            editions.parse(version)
            if editions.newer_than_known(version):
                raise FileFormatError(
                    f"this file is from Packet Tracer {version}, newer than any edition pktlib "
                    f"knows ({', '.join(f'{e} = {v}' for e, v in editions.EDITIONS.items())}); "
                    f"pass strict=False to read it anyway"
                )

    def _upgrade_refs(self) -> None:
        """Files from before Packet Tracer 8 (a 6.2 starter file) give devices
        no SAVE_REF_ID and point cables at a device's position in the list.
        8.2 points them at the SAVE_REF_ID, and pktlib only writes 8.2 files,
        so on load each device gets one and every cable end is repointed:
        the structural part of what Packet Tracer 8.2 does when it saves an
        old file. (It also adds new elements with default values; Packet
        Tracer fills those in itself when they're missing.)"""
        devs = list(self._devices_el) if self.root.find("NETWORK/DEVICES") is not None else []
        if not devs or all(d.find("ENGINE/SAVE_REF_ID") is not None for d in devs):
            return
        refs: dict[str, str] = {}
        for i, d in enumerate(devs):
            eng = req(d, "ENGINE")
            if eng.find("SAVE_REF_ID") is None:
                ET.SubElement(eng, "SAVE_REF_ID").text = f"save-ref-id:{self._rng.getrandbits(63)}"
            refs[str(i)] = req_text(eng, "SAVE_REF_ID")
        for cable in self.root.iter("CABLE"):
            for tag in ("FROM", "TO", "DCEDEV"):
                el = cable.find(tag)
                if el is not None and (el.text or "") in refs:
                    el.text = refs[el.text or ""]

    # load / save
    @classmethod
    def from_bytes(cls, data: bytes, *, seed: int | None = None, strict: bool = True) -> Network:
        """A network from .pkt bytes (see load() for a file)."""
        xml, level = decode_with_level(data)
        net = cls(parse_xml(xml), seed=seed, strict=strict)
        net._level = level
        return net

    @classmethod
    def from_xml(cls, xml: bytes | str, *, seed: int | None = None, strict: bool = True) -> Network:
        """A network from Packet Tracer's XML, as decode() gives it."""
        return cls(parse_xml(xml), seed=seed, strict=strict)

    @classmethod
    def new(cls, *, seed: int | None = None, edition: str = editions.LATEST) -> Network:
        """An empty network (Packet Tracer's blank workspace) for an edition
        pktlib knows; any other edition is an error."""
        stamp = editions.stamp(edition)
        net = cls(_template("base"), seed=seed)
        _set(net.root, "VERSION", stamp)
        return net

    @property
    def edition(self) -> str | None:
        """The Packet Tracer edition this file is for ('8.2'), or None for a
        release pktlib doesn't have (read with strict=False)."""
        try:
            return editions.edition_of(self.version)
        except PktError:
            return None

    def to_xml(self) -> bytes:
        """The XML, stamped as Packet Tracer 8.2 itself would save it: a file
        from an older release comes out stamped with the newest edition pktlib
        knows (its templates are from that release). A newer file read with
        strict=False keeps its own stamp."""
        latest = editions.stamp(editions.LATEST)
        if self._strict and editions.parse(self.version) < editions.parse(latest):
            _set(self.root, "VERSION", latest)
        return ET.tostring(self.root)

    def to_bytes(self) -> bytes:
        """The .pkt file's bytes: to_xml(), compressed (at the level the loaded
        file used, else Packet Tracer's 9) and encrypted."""
        return encode(self.to_xml(), self._level)

    def save(self, path: str | os.PathLike[str]) -> None:
        """Write the .pkt file."""
        Path(path).write_bytes(self.to_bytes())

    @property
    def version(self) -> str:
        return _text(self.root, "VERSION")

    # devices
    @property
    def _devices_el(self) -> ET.Element:
        return req(self.root, "NETWORK/DEVICES")

    @property
    def _links_el(self) -> ET.Element:
        return req(self.root, "NETWORK/LINKS")

    @property
    def devices(self) -> list[Device]:
        """Devices on the logical workspace (skips the power-distribution box)."""
        return [Device(self, d) for d in self._devices_el if _text(d, "ENGINE/TYPE") != "Power Distribution Device"]

    def device(self, name: Device | str) -> Device:
        """By name, or a Device of this network (handy where either is taken)."""
        if isinstance(name, Device):
            if not self._holds(name):
                raise NotFound(f"{name.name} isn't in this network")
            return name
        if not isinstance(name, str):
            raise TypeError(f"a device is a Device or its name, got {type(name).__name__}")
        for d in self.devices:
            if d.name == name:
                return d
        raise NotFound(f"no device called {name!r}")

    def __getitem__(self, name: str) -> Device:
        return self.device(name)

    def _taken(self) -> set[str]:
        """Every value in the file, upper-cased: what a new ID, MAC or address must not repeat."""
        return {el.text.strip().upper() for el in self.root.iter() if el.text and el.text.strip()}

    def _holds(self, device: Device) -> bool:
        return device.network is self and any(el is device.el for el in self._devices_el)

    def __contains__(self, device: object) -> bool:
        """A Device of this network, or a device name."""
        if isinstance(device, Device):
            return self._holds(device)
        return isinstance(device, str) and any(d.name == device for d in self.devices)

    def __iter__(self) -> Iterator[Device]:
        return iter(self.devices)

    def __len__(self) -> int:
        return len(self.devices)

    def __bool__(self) -> bool:
        return True  # an empty workspace is still a network

    def __repr__(self) -> str:
        d, n = len(self), len(self.links)
        return f"<Network {self.edition or self.version}: {d} device{'s' * (d != 1)}, {n} link{'s' * (n != 1)}>"

    def _by_ref(self, ref: str) -> Device | None:
        """The device a cable end points at. Files from 8.2 use the device's
        SAVE_REF_ID; older ones (6.2, seen in a lecturer's starter file) have no
        SAVE_REF_ID and use the device's position in the list, from 0."""
        devs = list(self._devices_el)
        for d in devs:
            if _text(d, "ENGINE/SAVE_REF_ID") == ref:
                return Device(self, d)
        if ref.isdigit() and int(ref) < len(devs) and devs[int(ref)].find("ENGINE/SAVE_REF_ID") is None:
            return Device(self, devs[int(ref)])
        return None

    def _physical_node(self, uuid_str: str) -> ET.Element | None:
        for n in req(self.root, "PHYSICALWORKSPACE").iter("NODE"):
            if _text(n, "UUID_STR") == uuid_str:
                return n
        return None

    def _renamed(self, old: str, new: str) -> None:
        pass  # links refer to devices by save-ref-id, so nothing else to update

    def _node_path(self, target: ET.Element) -> list[str] | None:
        """UUIDs from the top of the physical view down to `target`."""
        pw = req(self.root, "PHYSICALWORKSPACE")
        parents = {c: p for p in pw.iter() for c in p}
        if target not in parents and target is not pw:
            return None
        path, n = [], target
        while n is not pw:
            if n.tag == "NODE":
                path.append(_text(n, "UUID_STR"))
            n = parents[n]
        return path[::-1]

    def add_device(
        self, name: str, model: str, *, at: tuple[float, float] | None = None, unverified: bool = False
    ) -> Device:
        """Add any model in pktlib's spec: '2911', 'ISR4331', '3560-24PS',
        '1841+WIC-2T', 'PC-PT', '7960', ... (see pktlib.models()). Models whose
        port names nobody has checked against Packet Tracer are refused unless
        `unverified=True`. With no `at`, the device goes in the next free cell
        of a grid."""
        if not isinstance(model, str):
            raise TypeError(f"model is a string like '2911', got {model!r}")
        model = ALIASES.get(model, model)
        if model not in SPEC:  # '2960-24tt' is the 2960-24TT: model names differ by more than case
            model = next((m for m in SPEC if m.lower() == model.lower()), model)
        spec = SPEC.get(model)
        if spec is None:
            raise NotFound(
                f"unknown model {model!r}"
                + _suggest(model, list(SPEC) + list(ALIASES))
                + "; pktlib.models(verified_only=False) lists them"
            )
        if not spec["verified"] and not unverified:
            raise PktError(
                f"{model}'s port names aren't verified against Packet Tracer yet "
                f"(pass unverified=True to use it anyway)"
            )
        key = spec["template"]
        _check_name(name)
        at = (
            self._next_spot() if at is None else _check_xy(at)
        )  # before anything is added, so a bad position leaves no half-made device
        if name in self:
            raise PktError(f"there is already a device called {name!r}")

        pw = self.root.find("PHYSICALWORKSPACE/NODE")
        if pw is not None and pw.find("UUID_STR") is None:
            # a pre-8 workspace tree: an 8.2 device dropped into it made Packet
            # Tracer refuse the file ("corrupted Physical Workspace data")
            raise FileFormatError(
                "this file's physical workspace is from Packet Tracer before 8 (it says "
                f"{self.version}); open it in Packet Tracer 8.2 and save it once to convert it, "
                "then add devices with pktlib"
            )
        tpl = _template(key)
        dev_el = copy.deepcopy(req(tpl, "DEVICE"))
        node = copy.deepcopy(req(tpl, "NODE"))
        rng = self._rng
        # values already in the file aren't drawn again: a file loaded with the seed it was
        # built with would otherwise repeat its IDs and MACs (found by the state machine)
        taken = self._taken()
        eng = req(dev_el, "ENGINE")
        _set(eng, "NAME", name)
        _set(eng, "SAVE_REF_ID", _unique(lambda: f"save-ref-id:{rng.getrandbits(63)}", taken))
        if eng.find("SERIALNUMBER") is not None:
            _set(eng, "SERIALNUMBER", f"PTT{rng.randrange(10**10):010d}")
        # Every MAC in the template gets a fresh one: ports' MACADDRESS / BIA and
        # the device's own base address (ENGINE/BUILD_IN_ADDR, which switches use
        # as their bridge ID and SVI MAC). Two devices sharing one breaks STP,
        # ARP and HSRP between them. A mapping keeps equal values equal.
        fresh: dict[str, str] = {}
        for el in eng.iter():
            if el.text and _MAC_RE.fullmatch(el.text.strip()):
                old = el.text.strip().upper()
                if old not in fresh:
                    fresh[old] = _unique(lambda: _rand_mac(rng), taken)
                el.text = fresh[old]
        _refresh_link_locals(eng)
        # ports the template leaves untyped get the type Packet Tracer shows for them
        typed = [p for p in eng.iter("PORT") if p.find("TYPE") is not None]
        for i, t in (spec.get("fill_types") or {}).items():
            el = req(typed[int(i)], "TYPE")
            if not el.text:
                el.text = t
        for p in eng.iter("PORT"):
            for tag, val in (("IP", ""), ("SUBNET", ""), ("PORT_GATEWAY", ""), ("IPV6_DEFAULT_LINK_LOCAL", "")):
                if p.find(tag) is not None:
                    _set(p, tag, val)
        if eng.find("GATEWAY") is not None:
            _set(eng, "GATEWAY", "")
        _set(dev_el, "WORKSPACE/LOGICAL/MEM_ADDR", _unique(lambda: _rand_addr(rng), taken))
        _set(dev_el, "WORKSPACE/LOGICAL/DEV_ADDR", _unique(lambda: _rand_addr(rng), taken))

        # physical view: same container as the template, found by uuid, else by node type
        new_uuid = _unique(lambda: f"{{{uuid.UUID(int=rng.getrandbits(128), version=4)}}}", taken)
        _set(node, "UUID_STR", new_uuid)
        _set(node, "NAME", name)
        parent_path = _text(dev_el, "WORKSPACE/PHYSICAL").split(",")[:-1]
        parent = self._physical_node(parent_path[-1]) if parent_path else None
        if parent is None:
            want_type = tpl.get("parent_type", "4")
            parent = next(
                (n for n in req(self.root, "PHYSICALWORKSPACE").iter("NODE") if _text(n, "TYPE") == want_type), None
            )
            if parent is None:
                raise FileFormatError("this file has no rack/office in its physical view to put the device in")
            parent_path = self._node_path(parent) or []
        children = parent.find("CHILDREN")
        if children is None:
            children = ET.SubElement(parent, "CHILDREN")
        children.append(node)
        _set(dev_el, "WORKSPACE/PHYSICAL", ",".join(parent_path + [new_uuid]))
        cpur = dev_el.find("WORKSPACE/PHYSICAL_CPUR")
        if cpur is not None:
            if cpur.find("PARENT_PATH") is not None:
                _set(cpur, "PARENT_PATH", ",".join(parent_path))
            if cpur.find("CONTAINER_ID") is not None:
                _set(cpur, "CONTAINER_ID", parent_path[-1])

        self._devices_el.append(dev_el)
        dev = Device(self, dev_el)
        dev.xy = at
        if eng.find("SYS_NAME") is not None and dev.has_ios:
            _set(eng, "SYS_NAME", name)
        if dev.has_ios:
            if key == "router-1841-wic2t":  # taken from a configured router: start it from factory defaults
                dev.running_config = _default_router_config(name, list(dev.ports))
            else:  # catalogue templates are fresh off the palette
                dev.running_config = [
                    f"hostname {name}" if line.startswith("hostname ") else line for line in dev.running_config
                ]
            # each router gets its own licence serial, as two real ones would
            # (cloned 2911s all said `sn FTX1524ATOJ-`; found by the stress tests)
            sn = "FTX" + "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(8))
            dev.running_config = [
                re.sub(r"\bsn \S+", f"sn {sn}", line) if line.startswith("license udi ") else line
                for line in dev.running_config
            ]
        return dev

    def _end_device(
        self, name: str, model: str, at: tuple[float, float] | None, ip: Address | None, gateway: str
    ) -> Device:
        # every check before add_device, so a refusal leaves no half-made device
        if ip is None:
            if gateway:
                raise PktError("a gateway without an ip: pass ip='a.b.c.d/len' too")
            iface = None
        else:
            iface = _interface(ip)
            _gateway(gateway, iface)
        dev = self.add_device(name, model, at=at)
        if iface is not None:
            dev.set_ip(iface, gateway)
        return dev

    def router(self, name: str, model: str = "1841", *, at: tuple[float, float] | None = None) -> Device:
        """Add a router: '1841', '1841+WIC-2T' (two serial ports), '2911', 'ISR4331', ..."""
        return self.add_device(name, model, at=at)

    def switch(self, name: str, model: str = "2960-24TT", *, at: tuple[float, float] | None = None) -> Device:
        """Add a switch: '2960-24TT' (the default), '2950-24', 'Switch-PT', ..."""
        return self.add_device(name, model, at=at)

    def multilayer(self, name: str, model: str = "3560-24PS", *, at: tuple[float, float] | None = None) -> Device:
        """A layer 3 switch: VLANs, SVIs, `ip routing`, routed ports."""
        return self.add_device(name, model, at=at)

    def pc(
        self, name: str, *, at: tuple[float, float] | None = None, ip: Address | None = None, gateway: str = ""
    ) -> Device:
        """Add a PC; `ip` ('10.0.0.5/24' or '10.0.0.5 255.255.255.0') and `gateway` are optional."""
        return self._end_device(name, "PC-PT", at, ip, gateway)

    def laptop(
        self, name: str, *, at: tuple[float, float] | None = None, ip: Address | None = None, gateway: str = ""
    ) -> Device:
        """Add a laptop; `ip` and `gateway` as for pc()."""
        return self._end_device(name, "Laptop-PT", at, ip, gateway)

    def server(
        self, name: str, *, at: tuple[float, float] | None = None, ip: Address | None = None, gateway: str = ""
    ) -> Device:
        """Add a server; `ip` and `gateway` as for pc()."""
        return self._end_device(name, "Server-PT", at, ip, gateway)

    def printer(
        self, name: str, *, at: tuple[float, float] | None = None, ip: Address | None = None, gateway: str = ""
    ) -> Device:
        """Add a printer; `ip` and `gateway` as for pc()."""
        return self._end_device(name, "Printer-PT", at, ip, gateway)

    def phone(self, name: str, *, at: tuple[float, float] | None = None, power_adapter: bool = False) -> Device:
        """A Cisco 7960 IP phone. Ports: 'Switch' (to the access switch) and
        'PC' (daisy-chain a PC through it). Gets its address and line from
        DHCP / CME on a router, so no ip here. It needs power: a PoE switch
        (3560-24PS) or `power_adapter=True`."""
        dev = self.add_device(name, "7960", at=at)
        if power_adapter:
            dev.add_module("IP_PHONE_POWER_ADAPTER")
        return dev

    def _next_spot(self) -> tuple[float, float]:
        """Where a device with no `at=` goes: the next cell of a grid, left to
        right, eight to a row, so devices never land on top of each other."""
        i = len(self.devices)
        return 100 + 150 * (i % 8), 100 + 150 * (i // 8)

    def duplicate_macs(self) -> dict[str, list[str]]:
        """MAC -> ['CORE1 (base)', 'CORE2 (base)', ...] for any MAC found on
        more than one device. Should be empty: duplicates break STP, ARP and
        HSRP. (Within one device sharing is normal: an 1841's serial ports
        carry its Fa0/0 MAC.)"""
        seen: dict[str, dict[str, list[str]]] = {}
        for d in self.devices:
            base = _text(d.engine, "BUILD_IN_ADDR")
            if base:
                seen.setdefault(base.upper(), {}).setdefault(d.name, []).append(f"{d.name} (base)")
            for p in d.ports.values():
                if p.mac:
                    seen.setdefault(p.mac.upper(), {}).setdefault(d.name, []).append(f"{d.name}.{p.name}")
        return {m: [w for ws in by_dev.values() for w in ws] for m, by_dev in seen.items() if len(by_dev) > 1}

    def duplicate_link_locals(self) -> dict[str, list[str]]:
        """IPv6 link-local -> ['STAFF1.FastEthernet0', ...] for any stored on
        more than one device. Packet Tracer shows the stored value, so devices
        cloned without fixing it share an address."""
        seen: dict[str, dict[str, str]] = {}
        for d in self.devices:
            for p in d.ports.values():
                ll = _text(p.el, "IPV6_LINK_LOCAL").upper()
                if ll:
                    seen.setdefault(ll, {}).setdefault(d.name, f"{d.name}.{p.name}")
        return {ll: list(by_dev.values()) for ll, by_dev in seen.items() if len(by_dev) > 1}

    # drawings
    @property
    def shapes(self) -> list[Shape]:
        out = []
        for tag in ("RECTANGLES", "ELLIPSES"):
            el = self.root.find(tag)
            out += [] if el is None else [Shape(s) for s in el]
        return out

    @property
    def notes(self) -> list[Note]:
        el = self.root.find("PHYSICALWORKSPACE/NOTES")
        return [] if el is None else [Note(n) for n in el]

    def _shape(self, tag: str, box: tuple[float, float, float, float], outline: str | None, fill: str | None) -> Shape:
        el = make_shape(tag[:-1], box, outline, fill, _rand_addr(self._rng), self._rng)
        parent = self.root.find(tag)
        if parent is None:
            parent = ET.SubElement(self.root, tag)
        parent.append(el)
        return Shape(el)

    def rectangle(
        self, x1: float, y1: float, x2: float, y2: float, outline: str | None = "red", fill: str | None = None
    ) -> Shape:
        """Colours: a name (red, blue, green, ...) or '#rrggbb'."""
        return self._shape("RECTANGLES", (x1, y1, x2, y2), outline, fill)

    def ellipse(
        self, x1: float, y1: float, x2: float, y2: float, outline: str | None = "blue", fill: str | None = None
    ) -> Shape:
        """An ellipse inside the box (x1, y1)-(x2, y2); colours as for rectangle()."""
        return self._shape("ELLIPSES", (x1, y1, x2, y2), outline, fill)

    def note(self, text: str, at: tuple[float, float], *, html: bool = False) -> Note:
        """A text label on the workspace, shown as written. Packet Tracer reads
        a note as HTML, so `&`, `<` and `>` are escaped; with html=True the text
        is written as it is, markup and all ('<b>R1</b> is the core')."""
        parent = self.root.find("PHYSICALWORKSPACE/NOTES")
        if parent is None:
            parent = ET.SubElement(req(self.root, "PHYSICALWORKSPACE"), "NOTES")
        el = make_note(text, at, 40000 + 2 * len(parent), _rand_addr(self._rng), self._rng, as_html=html)
        parent.append(el)
        return Note(el)

    def around(
        self,
        *devices: Device | str,
        shape: Literal["ellipse", "rectangle"] = "ellipse",
        outline: str | None = None,
        fill: str | None = None,
        pad: float = 60,
        label: str | None = None,
    ) -> Shape:
        """A rectangle or ellipse enclosing `devices` (objects or names), with
        an optional label at its top-right, like the RIP / OSPF ovals in a
        brief. Ellipses get extra room since their corners are cut off."""
        if not devices:
            raise PktError("around() needs at least one device")
        if shape not in ("ellipse", "rectangle"):
            raise PktError("shape is 'ellipse' or 'rectangle'")
        if label is not None:
            check_note_text(label)  # before the shape is drawn, so a bad label leaves nothing behind
        pts = [self.device(d).xy for d in devices]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        grow = 1.45 if shape == "ellipse" else 1.0
        cx, cy = (min(xs) + max(xs)) / 2 + 20, (min(ys) + max(ys)) / 2 + 20  # xy is the icon's corner
        hw, hh = ((max(xs) - min(xs)) / 2 + pad) * grow, ((max(ys) - min(ys)) / 2 + pad) * grow
        box = (cx - hw, cy - hh, cx + hw, cy + hh)
        draw = self.ellipse if shape == "ellipse" else self.rectangle
        s = draw(*box, outline=outline or ("blue" if shape == "ellipse" else "red"), fill=fill)
        if label:
            self.note(label, at=(box[2] + 10, cy - 10) if shape == "ellipse" else (box[2] + 10, box[1]))
        return s

    @property
    def profile(self) -> Profile:
        """Options > User Profile: the name, email and other info a file is
        submitted under. Settable with a Profile, a tuple or just a name."""
        el = self.root.find("USER_PROFILE")
        if el is None:
            return Profile("")
        return Profile(el.findtext("NAME") or "", el.findtext("EMAIL") or "", el.findtext("ADDITIONAL_INFO") or "")

    @profile.setter
    def profile(self, value: Profile | tuple[str, ...] | str) -> None:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, tuple) or not 1 <= len(value) <= 3:
            raise TypeError(f"a profile is Profile(name, email, info), a tuple of those, or a name; got {value!r}")
        new = Profile(*value)
        for what, v in zip(("name", "email", "info"), new, strict=True):
            _check_str(v, f"the profile {what}")
        el = self.root.find("USER_PROFILE")
        if el is None:
            el = ET.SubElement(self.root, "USER_PROFILE")
        for tag, val in zip(("NAME", "EMAIL", "ADDITIONAL_INFO"), new, strict=True):
            sub = el.find(tag)
            if sub is None:
                sub = ET.SubElement(el, tag)
            sub.text = val or None

    # Simple PDUs: the ping checks listed under the workspace, one click each
    def _scenario(self, name: str | None) -> ET.Element:
        sset = self.root.find("SCENARIOSET")
        if sset is None:
            sset = ET.SubElement(self.root, "SCENARIOSET")
        scenarios = sset.findall("SCENARIO")
        found = next((s for s in scenarios if name is None or s.findtext("NAME") == name), None)
        if found is None and name and len(scenarios) == 1 and scenarios[0].find("PDU") is None:
            # every file has an empty "Scenario 0", and Packet Tracer shows the first
            # scenario on open: the first named one takes its place, not a slot behind it
            found = scenarios[0]
            req(found, "NAME").text = name
        if found is None:
            found = ET.SubElement(sset, "SCENARIO")
            ET.SubElement(found, "NAME", translate="true").text = name or "Scenario 0"
            ET.SubElement(found, "DESCRIPTION", translate="true")
        return found

    def ping(self, src: Device | str, dst: Device | str, ip: str | None = None, scenario: str | None = None) -> None:
        """A Simple PDU (ICMP echo) from `src` to `dst`, as the Add Simple PDU
        tool makes it: Packet Tracer lists it under the workspace and shows
        Successful or Failed when it's fired. `ip` defaults to dst's first
        address. `scenario` is a scenario's name; the first one by default, and
        a new name makes a new scenario. Copied from what Packet Tracer 8.2
        saved after adding one by hand (26 Oct 2026)."""
        s, d = self.device(src), self.device(dst)
        if scenario is not None:
            _check_str(scenario, "a scenario name")
        if ip is None:
            ip = next((p.ip for p in d.ports.values() if p.ip and p.up), "")
            if not ip:
                raise PktError(f"{d.name} has no address on a port that's up; pass ip=")
        else:
            _check_str(ip, "ip")
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                raise PktError(f"ip {ip!r} isn't an IPv4 address") from None
        pdu = ET.SubElement(self._scenario(scenario), "PDU")
        ET.SubElement(pdu, "TYPE", patterned="no").text = "0"
        ET.SubElement(pdu, "CUSTOM_TYPE")
        ET.SubElement(pdu, "SOURCE").text = s.ref
        ET.SubElement(pdu, "PORT")
        ET.SubElement(pdu, "DESTINATION", device=d.ref)
        # an opaque ARGB colour as a signed int, as Packet Tracer stores it
        ET.SubElement(pdu, "COLOR").text = str((0xFF << 24 | self._rng.getrandbits(24)) - (1 << 32))
        iph = ET.SubElement(pdu, "PDU")
        for tag, val in (("TYPE", "CIpHeader"), ("SRCADDR", None), ("DSTADDR", ip), ("PROTOCOL", None), ("TTL", "255")):
            ET.SubElement(iph, tag).text = val
        icmp = ET.SubElement(iph, "PDU")
        for tag, val in (
            ("TYPE", "CIcmpMessage"),
            ("ICMPTYPE", "8"),
            ("CODE", "0"),
            ("ID", "0"),
            ("SEQ", "0"),
            ("CHK", "0"),
        ):
            ET.SubElement(icmp, tag).text = val
        ET.SubElement(iph, "TOS").text = "0"
        for tag, val in (("TEST_CONDITION", "0"), ("POINTS", "1"), ("PDU_SIZE", "0"), ("START", "0")):
            ET.SubElement(pdu, tag).text = val

    @property
    def pdus(self) -> list[Pdu]:
        """Every Simple PDU: Pdu(scenario, source, destination, ip)."""
        out = []
        for sc in self.root.iterfind("SCENARIOSET/SCENARIO"):
            for pdu in sc.findall("PDU"):
                s, d = (
                    self._by_ref(pdu.findtext("SOURCE") or ""),
                    self._by_ref(req(pdu, "DESTINATION").get("device", "")),
                )
                out.append(
                    Pdu(
                        sc.findtext("NAME") or "",
                        s.name if s is not None else "?",
                        d.name if d is not None else "?",
                        pdu.findtext("PDU/DSTADDR") or "",
                    )
                )
        return out

    def remove_device(self, device: Device | str) -> None:
        """Delete a device with its cables and the ping checks that use it."""
        dev = self.device(device)
        name = dev.name
        for sc in self.root.iterfind("SCENARIOSET/SCENARIO"):  # its PDUs would point at nothing
            for pdu in sc.findall("PDU"):
                if dev.ref in (pdu.findtext("SOURCE"), req(pdu, "DESTINATION").get("device")):
                    sc.remove(pdu)
        for link in [lk for lk in self.links if name in (lk.ends[0][0], lk.ends[1][0])]:
            self._links_el.remove(link.el)
        node = self._physical_node(dev.uuid)
        if node is not None:
            pw = req(self.root, "PHYSICALWORKSPACE")
            parents = {c: p for p in pw.iter() for c in p}
            parents[node].remove(node)
        self._devices_el.remove(dev.el)

    # links
    @property
    def links(self) -> list[Link]:
        return [Link(self, el) for el in self._links_el]

    def link_at(self, device: Device | str, port: str) -> Link | None:
        """The cable in a device's port, or None."""
        dev = self.device(device)
        want = (dev.name, dev.port(port).name)
        for link in self.links:
            if want in link.ends:
                return link
        return None

    def auto_cable(self, a: Port, b: Port) -> Cable:
        """The cable that brings the link up in Packet Tracer: serial for
        serial; straight to or from an IP phone (switch to phone, phone to PC);
        straight between a switch-like port and anything else; cross otherwise.
        A port is switch-like by its device and, on home routers, by which port
        it is: their LAN ports are, their Internet port isn't."""
        if is_serial(a.name) or is_serial(b.name):
            return "serial"
        for p in (a, b):
            if p.type in _PORT_CABLE:
                return _PORT_CABLE[p.type]
        if "IpPhone" in (a.device.kind, b.device.kind):
            return "straight"
        return "straight" if _switch_like(a) != _switch_like(b) else "cross"

    def connect(self, a: Device | str, a_port: str, b: Device | str, b_port: str, cable: Cable | None = None) -> Link:
        """Cable a.a_port to b.b_port. cable: 'straight', 'cross', 'serial',
        'coax', 'phone' or None to pick the right one. For serial, `a` is the
        DCE end."""
        da, db = self.device(a), self.device(b)
        pa, pb = da.port(a_port), db.port(b_port)
        if da.name == db.name and pa.name == pb.name:
            raise PktError("can't cable a port to itself")
        if da.name == db.name:
            # check 8, 2026-10-26: Packet Tracer dropped SW1 Fa0/1 to Fa0/2 on load
            raise PktError(f"{da.name}: Packet Tracer drops a cable between two ports of one device")
        for p in (pa, pb):
            if self.link_at(p.device.name, p.name):
                raise PktError(f"{p.device.name}.{p.name} already has a cable")
        if is_serial(pa.name) != is_serial(pb.name):
            raise PktError(f"{da.name}.{pa.name} and {db.name}.{pb.name}: serial only joins serial")
        if pa.type == "eBluetooth" or pb.type == "eBluetooth":
            raise PktError("Bluetooth ports don't take cables")
        for d, p in ((da, pa), (db, pb)):
            # Packet Tracer refuses a whole file whose cable names a port it doesn't know
            if p.type not in CABLE_TYPES:
                raise PktError(f"{d.name}.{p.name} isn't a cable port")
        if cable is None:
            cable = self.auto_cable(pa, pb)
        if cable not in _CABLES:
            raise PktError(f"unknown cable {cable!r} ({', '.join(_CABLES)})")
        for d, p in ((da, pa), (db, pb)):
            # each cable fits one kind of port: coax to coax, phone to phone, serial to serial
            fits = _PORT_CABLE.get(p.type) or ("serial" if is_serial(p.name) else "ethernet")
            if fits != {"straight": "ethernet", "cross": "ethernet"}.get(cable, cable):
                raise PktError(f"a {cable} cable doesn't fit {d.name}.{p.name}")

        rng = self._rng
        link = ET.Element("LINK")
        ET.SubElement(link, "TYPE").text = _CABLE_MEDIUM[cable]
        c = ET.SubElement(link, "CABLE")
        for tag, val in (
            ("LENGTH", "1"),
            ("FUNCTIONAL", "true"),
            ("FROM", da.ref),
            ("PORT", pa.name),
            ("TO", db.ref),
            ("PORT", pb.name),
            ("FROM_DEVICE_MEM_ADDR", da.dev_addr),
            ("TO_DEVICE_MEM_ADDR", db.dev_addr),
            ("FROM_PORT_MEM_ADDR", _rand_addr(rng)),
            ("TO_PORT_MEM_ADDR", _rand_addr(rng)),
            ("GEO_VIEW_COLOR", _CABLE_COLOUR[cable]),
            ("IS_MANAGED_IN_RACK_VIEW", "false"),
        ):
            ET.SubElement(c, tag).text = val
        if cable == "serial":
            ET.SubElement(c, "DCEDEV").text = da.ref
            ET.SubElement(c, "DCEPORT").text = pa.name
        elif cable in ("straight", "cross"):
            ET.SubElement(c, "TYPE").text = "eStraightThrough" if cable == "straight" else "eCrossOver"
        self._links_el.append(link)
        return Link(self, link)

    def disconnect(self, device: Device | str, port: str) -> None:
        """Pull the cable out of a device's port."""
        link = self.link_at(device, port)
        if link is None:
            dev = self.device(device)
            raise NotFound(f"{dev.name}.{dev.port(port).name} has no cable")
        self._links_el.remove(link.el)

    # notes on the logical workspace aren't modelled yet; they survive load/save.


def load(path: str | os.PathLike[str], *, seed: int | None = None, strict: bool = True) -> Network:
    """Open a .pkt. strict=False reads one from a Packet Tracer pktlib doesn't know."""
    xml, level = decode_with_level(Path(path).read_bytes())
    root = parse_xml(xml)
    if root.tag == "PACKETTRACER5_ACTIVITY":
        raise FileFormatError(
            f"{path} is a Packet Tracer activity (.pka), not a network; read it with pktlib.activity.load_activity()"
        )
    net = Network(root, seed=seed, strict=strict)
    net._level = level
    return net


def new(*, seed: int | None = None, edition: str = editions.LATEST) -> Network:
    """A blank network for a Packet Tracer edition pktlib knows (default: the newest)."""
    return Network.new(seed=seed, edition=edition)
