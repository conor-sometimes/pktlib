"""Hardware slots and the modules in them: WIC cards, power supplies, host NICs.

Packet Tracer nests them: a device's root MODULE holds SLOTs, a SLOT has a TYPE
(what fits) and at most one MODULE, and a module can hold more SLOTs. Ports
sit on modules. Router interface names follow the nesting:
`<type><bay>/<slot>/<port>`, e.g. a WIC-2T in an 1841's second WIC slot gives
Serial0/1/0 and Serial0/1/1.
"""

from __future__ import annotations

import copy
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from importlib import resources

from ._errors import NotFound
from ._ports import _PREFIX
from ._xml import req, req_attr

# Friendly words for slot types, used in errors and docs.
SLOT_WORDS = {
    "eInterfaceCard": "interface-card slot (WIC/HWIC/NIM)",
    "ePtSwitchModule": "power-supply bay",
    "eSfpModule": "SFP slot",
    "ePtHostModule": "host module slot",
    "eTrs35": "USB slot",
    "eNetworkModule": "network-module bay",
}


@dataclass
class Slot:
    """One place a module can go. `path` is the slot's index at each level
    from the device's root module down, e.g. (0, 1) is an 1841's 2nd WIC slot."""

    el: ET.Element
    path: tuple[int, ...]

    @property
    def type(self) -> str:
        return self.el.findtext("TYPE") or ""

    @property
    def module(self) -> ET.Element | None:
        return self.el.find("MODULE")

    @property
    def model(self) -> str | None:
        m = self.module
        return None if m is None else (m.findtext("MODEL") or "")

    @property
    def removable(self) -> bool:
        return not self.type.startswith("eNonRemovable")

    @property
    def empty(self) -> bool:
        return self.module is None

    def __repr__(self) -> str:
        what = self.model if not self.empty else "empty"
        return f"<Slot {'/'.join(map(str, self.path))} {SLOT_WORDS.get(self.type, self.type)}: {what}>"


def slots(root_module: ET.Element) -> list[Slot]:
    """Every slot under a device's root MODULE, depth first."""
    out: list[Slot] = []

    def walk(mod: ET.Element, path: tuple[int, ...]) -> None:
        for i, s in enumerate(mod.findall("SLOT")):
            here = path + (i,)
            out.append(Slot(s, here))
            m = s.find("MODULE")
            if m is not None:
                walk(m, here)

    walk(root_module, ())
    return out


def _catalogue() -> dict[str, tuple[str, ET.Element]]:
    raw = resources.files("pktlib").joinpath("data").joinpath("modules.xml.gz").read_bytes()
    root = ET.fromstring(gzip.decompress(raw))
    return {req_attr(e, "model"): (req_attr(e, "slot_type"), req(e, "MODULE")) for e in root}


_CATALOGUE: dict[str, tuple[str, ET.Element]] | None = None


def catalogue() -> dict[str, tuple[str, ET.Element]]:
    """Module model -> (slot type it fits, its XML), as Packet Tracer made them."""
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = _catalogue()
    return _CATALOGUE


def module_models() -> list[str]:
    """Every module model pktlib can fit, sorted."""
    return sorted(catalogue())


def fresh_module(model: str) -> tuple[str, ET.Element]:
    """(slot type, a fresh copy of the module's XML) for a module model."""
    if model not in catalogue():
        raise NotFound(f"unknown module {model!r}; pktlib knows {', '.join(module_models())}")
    slot_type, el = catalogue()[model]
    return slot_type, copy.deepcopy(el)


# Routers whose onboard WIC slots share one two-level numbering: a WIC-2T in
# each slot of a 2620XM or 2621XM is Serial0/0-0/1 and Serial0/2-0/3, never
# Serial0/0/0 (Packet Tracer 8.2's Config tab, 27 Oct 2026). A cable to the
# three-level name made Packet Tracer refuse the whole file.
_FLAT_WIC_MODELS = {"2620XM": 2, "2621XM": 2}  # model -> ports per WIC slot


def port_names_for(module: ET.Element, path: tuple[int, ...], model: str = "") -> list[tuple[ET.Element, str]]:
    """IOS names for the ports on `module` sitting at slot `path` (routers:
    0-based, `<type><bay>/<slot>/<port>`) in a `model` router."""
    out = []
    counts: dict[str, int] = {}
    flat = _FLAT_WIC_MODELS.get(model) if len(path) == 2 and path[0] == 0 else None
    for p in module.findall("PORT"):
        prefix = _PREFIX.get(p.findtext("TYPE") or "")
        if prefix is None:
            continue
        i = counts.get(prefix, 0)
        counts[prefix] = i + 1
        name = f"{prefix}0/{path[1] * flat + i}" if flat else f"{prefix}{'/'.join(map(str, path))}/{i}"
        out.append((p, name))
    return out
