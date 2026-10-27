"""Port names: Packet Tracer's, IOS's and the shorthand people type."""

from __future__ import annotations

import re

from ._errors import PktError

_PREFIX = {
    "eCopperFastEthernet": "FastEthernet",
    "eFiberFastEthernet": "FastEthernet",
    "eCopperGigabitEthernet": "GigabitEthernet",
    "eFiberGigabitEthernet": "GigabitEthernet",
    "eCopperEthernet": "Ethernet",
    "eCopperGigabitManagement": "Management",
    "eSmartSerial": "Serial",
    "eSerial": "Serial",
    "eBluetooth": "Bluetooth",
    "eWireless": "Wireless",
}
_ALIASES = {
    "gigabitethernet": "GigabitEthernet",
    "gig": "GigabitEthernet",
    "gi": "GigabitEthernet",
    "g": "GigabitEthernet",
    "fastethernet": "FastEthernet",
    "fa": "FastEthernet",
    "f": "FastEthernet",
    "ethernet": "Ethernet",
    "eth": "Ethernet",
    "e": "Ethernet",
    "serial": "Serial",
    "se": "Serial",
    "s": "Serial",
    "bluetooth": "Bluetooth",
    "wireless": "Wireless",
    "vlan": "Vlan",
    "vl": "Vlan",
    "loopback": "Loopback",
    "lo": "Loopback",
    "port-channel": "Port-channel",
    "po": "Port-channel",
    "management": "Management",
    "mgmt": "Management",
    "ma": "Management",
}
# type, slot/port numbers, optional .subinterface
_PORT_RE = re.compile(r"([A-Za-z]+(?:-[A-Za-z]+)?)\s*([0-9]+(?:/[0-9]+)*)(?:\.([0-9]+))?")


def canonical_port(name: str) -> str:
    """'fa0/1', 'F0/1', 'FastEthernet 0/1' -> 'FastEthernet0/1'; 'fa0/0.10' ->
    'FastEthernet0/0.10'; 'vlan 1' -> 'Vlan1'."""
    if not isinstance(name, str):
        raise TypeError(f"a port name is a string, got {type(name).__name__}")
    m = _PORT_RE.fullmatch(name.strip())
    if not m:
        raise PktError(f"not a port name: {name!r}")
    full = _ALIASES.get(m[1].lower())
    if full is None:
        raise PktError(f"unknown interface type in {name!r}")
    return full + m[2] + (f".{m[3]}" if m[3] is not None else "")


def expand_range(spec: str) -> list[str]:
    """The argument of `interface range`: 'fa0/1 - 3', 'g1/0/23 - 24',
    'fa0/1 - 2 , fa0/5' -> canonical names, in order."""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part and not re.match(r"(?i)port-channel", part):
            first, last = (x.strip() for x in part.rsplit("-", 1))
            start = canonical_port(first)
            m = re.fullmatch(r"(.*?)(\d+)", start)
            if not m or not last.isdigit() or int(last) < int(m[2]) or int(last) - int(m[2]) > 512:
                raise PktError(f"bad interface range {part!r}")
            out += [f"{m[1]}{i}" for i in range(int(m[2]), int(last) + 1)]
        else:
            out.append(canonical_port(part))
    return out


# Port types pktlib can put a cable on: copper or fibre Ethernet (straight or
# cross-over), serial, coax and phone line. Radios take none.
CABLE_TYPES = frozenset(
    {
        t
        for t, prefix in _PREFIX.items()
        if prefix in ("FastEthernet", "GigabitEthernet", "Ethernet", "Serial", "Management")
    }
    | {"eCopperCoaxial", "eModem"}
)


def is_serial(port_name: str) -> bool:
    """Whether a port name is a serial port ('Serial0/0/0', 'se0/1/0')."""
    return port_name.startswith("Serial")


_IOS_ORDER = [
    "Ethernet",
    "FastEthernet",
    "GigabitEthernet",
    "Management",
    "Serial",
    "Bluetooth",
    "Wireless",
    "Loopback",
    "Port-channel",
    "Vlan",
]


def port_sort_key(name: str) -> tuple[int, tuple[int, ...], int, str]:
    """IOS order: FastEthernet0/0, FastEthernet0/0.10, FastEthernet0/1, Serial0/0/0, ..."""
    m = _PORT_RE.fullmatch(name)
    if not m:
        return (len(_IOS_ORDER) + 1, (), -1, name)
    rank = _IOS_ORDER.index(m[1]) if m[1] in _IOS_ORDER else len(_IOS_ORDER)
    return (rank, tuple(int(x) for x in m[2].split("/")), int(m[3]) if m[3] else -1, "")
