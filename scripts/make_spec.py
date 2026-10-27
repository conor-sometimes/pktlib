"""Write src/pktlib/spec/devices.json: what pktlib knows about each model.

    uv run python scripts/make_spec.py

Port names come from Packet Tracer, not from pktlib's naming code:
  ios-config   the device's own `interface` lines in its fresh running config,
               counted per type against the ports in the file (they must match)
  pt-menu      read off Packet Tracer's cable menu by hand (MANUAL below)
  pt-hover     read off Packet Tracer's hover table and matched port by port
               by MAC address (HOVER below)
A model whose names can't be confirmed either way is written with
"verified": false; pktlib loads such devices but won't create them.
Review the diff before committing: the spec is what the tests hold pktlib to.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pktlib._modules import slots  # noqa: E402
from pktlib._ports import _PORT_RE, _PREFIX, CABLE_TYPES  # noqa: E402
from pktlib._xml import req, req_attr, req_text  # noqa: E402

DATA = ROOT / "src" / "pktlib" / "data"
OUT = ROOT / "src" / "pktlib" / "spec" / "devices.json"
WIRED = ("FastEthernet", "GigabitEthernet", "Ethernet", "Serial", "Management")

# Seen in Packet Tracer 8.2.0's cable menu (Connections, click the device), 25 Oct 2026.
# port_names follow the order the ports sit in the file.
MANUAL = {
    "PC-PT": {"port_names": ["FastEthernet0", "Bluetooth"], "wired": ["FastEthernet0"]},
    "Laptop-PT": {"port_names": ["FastEthernet0", "Bluetooth"], "wired": ["FastEthernet0"]},
    "Server-PT": {"port_names": ["FastEthernet0"], "wired": ["FastEthernet0"]},
    "Meraki-Server": {"port_names": ["FastEthernet0"], "wired": ["FastEthernet0"]},
    "Printer-PT": {"port_names": ["FastEthernet0"], "wired": ["FastEthernet0"]},
    "WiredEndDevice-PT": {"port_names": ["FastEthernet0"], "wired": ["FastEthernet0"]},
    "7960": {"port_names": ["Switch", "PC"], "wired": ["Switch", "PC"]},
}
# Read off Packet Tracer 8.2.0's hover table (point at the device), 25 Oct 2026.
# Names are in file order; each one was matched to its port by MAC address, so
# hidden ports PT never lists are None. fill_types gives ports the template
# leaves without a TYPE the type PT shows for them: a cable into a port with no
# type makes PT refuse the whole file ("not compatible with this version").
_FE, _GE = "FastEthernet", "GigabitEthernet"
HOVER = {
    "IE-2000": {
        "port_names": [f"{_FE}1/{i}" for i in range(1, 9)] + [f"{_GE}1/1", f"{_GE}1/2"],
        "fill_types": dict.fromkeys(range(4), "eCopperFastEthernet"),
    },
    "819HGW": {
        "port_names": [
            f"{_GE}0",
            f"{_FE}0",
            f"{_FE}1",
            f"{_FE}2",
            f"{_FE}3",
            "Serial0",
            "Wlan-GigabitEthernet0",
            "wlan-ap0",
            "Cellular0",
            None,
            None,
            None,
        ]
    },
    "829": {
        "port_names": [f"{_GE}{i}" for i in range(5)]
        + ["wlan-ap0", "Wlan-GigabitEthernet0", f"{_GE}5", "Cellular0", "Cellular1"]
        + [None] * 5
    },
    "819HG-4G-IOX": {
        "port_names": [
            f"{_GE}0",
            f"{_FE}0",
            f"{_FE}1",
            f"{_FE}2",
            f"{_FE}3",
            "Serial0",
            "Ethernet1",
            "VirtualPortGroup0",
            "Cellular0",
            None,
            None,
        ]
    },
    "CGR1240": {
        "port_names": [
            f"{_GE}0/1",
            f"{_FE}2/3",
            f"{_FE}2/4",
            f"{_FE}2/5",
            f"{_FE}2/6",
            f"{_GE}2/1",
            f"{_GE}2/2",
            "Dot11Radio2/1",
        ]
    },
    "3702i": {"port_names": [f"{_GE}0", "Dot11Radio0"]},
    "LAP-PT": {"port_names": [f"{_GE}0", "Dot11Radio0"]},
    "Hub-PT": {"port_names": [f"{_FE}{i}" for i in range(6)]},
    "Bridge-PT": {"port_names": ["Ethernet0/1", "Ethernet1/1"]},
    # home and small-office kit names ports as its GUI does, spaces and all
    "Linksys-WRT300N": {"port_names": ["Internet", "Ethernet 1", "Ethernet 2", "Ethernet 3", "Ethernet 4", "Wireless"]},
    "DLC100": {"port_names": ["Internet", "Ethernet 1", "Ethernet 2", "Ethernet 3", "Ethernet 4", "Wireless"]},
    "HomeRouter-PT-AC": {
        "port_names": ["Internet"]
        + [f"{_GE} {i}" for i in range(1, 5)]
        + [f"Wireless {i}" for i in range(1, 7)]
        + ["Wireless0/0"]
    },
    "WLC-2504": {"port_names": [f"{_GE}{i}" for i in range(1, 5)] + [None, "management", None]},
    "WLC-3504": {
        "port_names": [f"{_GE}{i}" for i in range(1, 6)] + [None, "management", None],
        "fill_types": {2: "eCopperGigabitEthernet", 3: "eCopperGigabitEthernet"},
    },
    "WLC-PT": {"port_names": [f"{_GE}0", "Management"]},
    "NetworkController": {"port_names": [f"{_GE}0", f"{_GE}1"]},
    "Repeater-PT": {"port_names": ["Ethernet0", "Ethernet1"]},
    "Sniffer": {"port_names": ["Ethernet0", "Ethernet1"]},
    "Central-Office-Server": {"port_names": ["Backbone"] + [f"Coaxial0/{i}" for i in range(6)] + ["Cellular0/0"]},
    "TV-PT": {"port_names": ["Port 0"]},
    "Analog-Phone-PT": {"port_names": ["Port 0"]},
    "CoAxialSplitter-PT": {"port_names": ["Coaxial0", "Coaxial1", "Coaxial2"]},
    "Cell-Tower": {"port_names": ["Coaxial0", "3G/4G Server1"]},
    # read off the cable menu (click a cable, then the device): it lists every
    # cable port by name in file order (Cloud-PT: serials, modems, Ethernet6, Coaxial7)
    "Cloud-PT": {"port_names": [f"Serial{i}" for i in range(4)] + ["Modem4", "Modem5", "Ethernet6", "Coaxial7"]},
    "Home-VoIP-PT": {"port_names": ["Ethernet", "Phone"]},
    "Meraki-MX65W": {
        "port_names": ["Internet 1", "Internet 2"]
        + [f"{_GE} {i}" for i in range(3, 11)]
        + ["Ethernet 11", "Ethernet 12", None],
        "fill_types": {10: "eCopperEthernet", 11: "eCopperEthernet"},
    },
    "SMARTPHONE-PT": {"port_names": ["Wireless0", "3G/4G Cell1", "Bluetooth"]},
    "TabletPC-PT": {"port_names": ["Wireless0", "3G/4G Cell1", "Bluetooth"]},
    "WirelessEndDevice-PT": {"port_names": ["Wireless0"]},
    # empty chassis: no ports until a module goes in
    "Cloud-PT-Empty": {"port_names": []},
    "Router-PT-Empty": {"port_names": []},
    "Switch-PT-Empty": {"port_names": []},
    # these list no MACs; the order is the file's, as on the APs, whose radio
    # (always up) is Port 1, and checked by cabling Port 0 / Port 1 in PT
    **{
        m: {"port_names": ["Port 0", "Port 1"]}
        for m in (
            "AccessPoint-PT",
            "AccessPoint-PT-A",
            "AccessPoint-PT-AC",
            "AccessPoint-PT-N",
            "Cable-Modem-PT",
            "DSL-Modem-PT",
        )
    },
}
# Each model's Physical-tab MODULES list in Packet Tracer 8.2.0, read by hand on
# 25 Oct 2026: what the GUI lets you drag in. `add_module` refuses anything else.
_ISR_G2 = ["HWIC-1GE-SFP", "HWIC-2T", "HWIC-4ESW", "HWIC-8A", "WIC-Cover", "GLC-LH-SMD"]
_1841 = [
    "HWIC-1GE-SFP",
    "HWIC-2T",
    "HWIC-4ESW",
    "HWIC-8A",
    "HWIC-AP-AG-B",
    "WIC-1AM",
    "WIC-1ENET",
    "WIC-1T",
    "WIC-2AM",
    "WIC-2T",
    "WIC-Cover",
    "GLC-LH-SMD",
]
_NM = [
    "NM-1E",
    "NM-1E2W",
    "NM-1FE-FX",
    "NM-1FE-TX",
    "NM-1FE2W",
    "NM-2E2W",
    "NM-2FE2W",
    "NM-2W",
    "NM-4A/S",
    "NM-4E",
    "NM-8A/S",
    "NM-8AM",
    "NM-Cover",
]
_HOST = [
    "WMP300N",
    "PT-HOST-NM-1CE",
    "PT-HOST-NM-1CFE",
    "PT-HOST-NM-1CGE",
    "PT-HOST-NM-1FFE",
    "PT-HOST-NM-1FGE",
    "PT-HOST-NM-1W",
    "PT-HOST-NM-1W-A",
    "PT-HOST-NM-1W-AC",
    "PT-HOST-NM-3G/4G",
    "PT-HOST-NM-COVER",
]
_CLOUD = [
    "PT-CLOUD-NM-1AM",
    "PT-CLOUD-NM-1CE",
    "PT-CLOUD-NM-1CFE",
    "PT-CLOUD-NM-1CGE",
    "PT-CLOUD-NM-1CX",
    "PT-CLOUD-NM-1FFE",
    "PT-CLOUD-NM-1FGE",
    "PT-CLOUD-NM-1S",
]
_REPEATER = [
    "PT-REPEATER-NM-1CE",
    "PT-REPEATER-NM-1CFE",
    "PT-REPEATER-NM-1CGE",
    "PT-REPEATER-NM-1FFE",
    "PT-REPEATER-NM-1FGE",
    "PT-REPEATER-NM-COVER",
]
ACCEPTS = {
    "ISR4331": ["NIM-2T", "NIM-Cover", "NIM-ES2-4", "GLC-GE-100FX", "GLC-LH-SMD", "GLC-T", "GLC-TE"],
    "ISR4321": ["NIM-2T", "NIM-Cover", "NIM-ES2-4", "GLC-GE-100FX", "GLC-LH-SMD"],
    "1941": _ISR_G2,
    "2901": _ISR_G2,
    "2911": _ISR_G2,
    "1841": _1841,
    "1841+WIC-2T": _1841,
    "2620XM": _NM + ["WIC-1AM", "WIC-1T", "WIC-2AM", "WIC-2T", "WIC-Cover"],
    "2621XM": _NM + ["WIC-1AM", "WIC-1T", "WIC-2AM", "WIC-2T", "WIC-Cover"],
    "2811": _NM
    + [
        "NM-ESW-161",
        "HWIC-1GE-SFP",
        "HWIC-2T",
        "HWIC-4ESW",
        "HWIC-8A",
        "HWIC-AP-AG-B",
        "WIC-1AM",
        "WIC-1ENET",
        "WIC-1T",
        "WIC-2AM",
        "WIC-2T",
        "WIC-Cover",
    ],
    "Router-PT": [
        "PT-ROUTER-NM-1AM",
        "PT-ROUTER-NM-1CE",
        "PT-ROUTER-NM-1CFE",
        "PT-ROUTER-NM-1CGE",
        "PT-ROUTER-NM-1FFE",
        "PT-ROUTER-NM-1FGE",
        "PT-ROUTER-NM-1S",
        "PT-ROUTER-NM-1SS",
        "PT-ROUTER-NM-COVER",
    ],
    "Switch-PT": [
        "PT-SWITCH-NM-1CE",
        "PT-SWITCH-NM-1CFE",
        "PT-SWITCH-NM-1CGE",
        "PT-SWITCH-NM-1FFE",
        "PT-SWITCH-NM-1FGE",
        "PT-SWITCH-NM-COVER",
    ],
    "3650-24PS": ["AC-POWER-SUPPLY", "POWER-COVER-PLATE", "GLC-LH-SMD", "GLC-T", "GLC-TE"],
    "2960-24TT": [],
    "3560-24PS": [],
    "2950-24": [],
    "2950T-24": [],
    "5505": [],
    "WiredEndDevice-PT": [],
    "PC-PT": ["WMP300N", "PT-HOST-NM-1AM"] + _HOST[1:] + ["PT-HEADPHONE", "PT-MICROPHONE"],
    "Laptop-PT": [
        "WPC300N",
        "PT-LAPTOP-NM-1AM",
        "PT-LAPTOP-NM-1CE",
        "PT-LAPTOP-NM-1CFE",
        "PT-LAPTOP-NM-1CGE",
        "PT-LAPTOP-NM-1FFE",
        "PT-LAPTOP-NM-1FGE",
        "PT-LAPTOP-NM-1W",
        "PT-LAPTOP-NM-1W-A",
        "PT-LAPTOP-NM-1W-AC",
        "PT-LAPTOP-NM-3G/4G",
        "PT-HEADPHONE",
        "PT-MICROPHONE",
    ],
    "Server-PT": _HOST,
    "Meraki-Server": _HOST,
    "Printer-PT": _HOST,
    "7960": ["IP_PHONE_POWER_ADAPTER"],
    "5506-X": [],
    "IE-2000": [],
    "819HGW": [],
    "819HG-4G-IOX": [],
    "829": ["GLC-T", "GLC-TE"],
    "CGR1240": ["1240-Cover", "ROUTER-ADAPTER", "GLC-FE-100FX-RGD"],
    "3702i": ["ACCESS_POINT_POWER_ADAPTER"],
    "LAP-PT": ["ACCESS_POINT_POWER_ADAPTER"],
    "Hub-PT": _REPEATER,
    "Repeater-PT": _REPEATER,
    "Sniffer": _REPEATER,
    "AccessPoint-PT": _REPEATER,
    "AccessPoint-PT-A": _REPEATER,
    "AccessPoint-PT-AC": _REPEATER,
    "AccessPoint-PT-N": _REPEATER,
    "Cable-Modem-PT": ["PT-MODEM-NM-1CE", "PT-MODEM-NM-1CFE", "PT-MODEM-NM-1CGE"],
    "DSL-Modem-PT": ["PT-MODEM-NM-1CE", "PT-MODEM-NM-1CFE", "PT-MODEM-NM-1CGE"],
    "Linksys-WRT300N": [],
    "DLC100": [],
    "HomeRouter-PT-AC": [],
    "WLC-2504": [],
    "WLC-3504": [],
    "WLC-PT": [],
    "NetworkController": [],
    "Central-Office-Server": [],
    "TV-PT": [],
    "Analog-Phone-PT": [],
    "CoAxialSplitter-PT": [],
    "Cell-Tower": ["PT-CELL-NM-1CX", "PT-CELL-NM-3G/4G"],
    "Cloud-PT": _CLOUD,
    "Cloud-PT-Empty": _CLOUD,
    "Router-PT-Empty": [
        "PT-ROUTER-NM-1AM",
        "PT-ROUTER-NM-1CE",
        "PT-ROUTER-NM-1CFE",
        "PT-ROUTER-NM-1CGE",
        "PT-ROUTER-NM-1FFE",
        "PT-ROUTER-NM-1FGE",
        "PT-ROUTER-NM-1S",
        "PT-ROUTER-NM-1SS",
        "PT-ROUTER-NM-COVER",
    ],
    "Switch-PT-Empty": [
        "PT-SWITCH-NM-1CE",
        "PT-SWITCH-NM-1CFE",
        "PT-SWITCH-NM-1CGE",
        "PT-SWITCH-NM-1FFE",
        "PT-SWITCH-NM-1FGE",
        "PT-SWITCH-NM-COVER",
    ],
    "Meraki-MX65W": ["MERAKI-POWER-ADAPTER"],
    "Home-VoIP-PT": [],
    "SMARTPHONE-PT": [],
    "TabletPC-PT": [],
    "WirelessEndDevice-PT": [],
    "Bridge-PT": [
        "PT-SWITCH-NM-1CE",
        "PT-SWITCH-NM-1CFE",
        "PT-SWITCH-NM-1CGE",
        "PT-SWITCH-NM-1FFE",
        "PT-SWITCH-NM-1FGE",
        "PT-SWITCH-NM-COVER",
    ],
}
FAMILY = {  # Packet Tracer kind -> the word pktlib's helpers use
    "Router": "router",
    "Switch": "switch",
    "MultiLayerSwitch": "multilayer",
    "Pc": "pc",
    "Laptop": "laptop",
    "Server": "server",
    "MerakiServer": "server",
    "Printer": "printer",
    "IpPhone": "phone",
    "WiredEndDevice": "end-device",
    "Hub": "hub",
}


def main() -> None:
    spec = {}
    for f in sorted(DATA.glob("*.xml.gz")):
        if f.name in ("base.xml.gz", "modules.xml.gz"):
            continue
        tpl = ET.fromstring(gzip.decompress(f.read_bytes()))
        eng = req(tpl, "DEVICE/ENGINE")
        kind, model = req_text(eng, "TYPE"), req_attr(req(eng, "TYPE"), "model")
        key = "1841+WIC-2T" if tpl.get("key") == "router-1841-wic2t" else model
        types = [p.findtext("TYPE") or "" for p in eng.iter("PORT") if p.find("TYPE") is not None]
        root_module = eng.find("MODULE")
        tree = slots(root_module) if root_module is not None else []
        rc = eng.find("RUNNINGCONFIG")
        ios = rc is not None
        entry: dict[str, object] = {
            "kind": kind,
            "family": FAMILY.get(kind, kind.lower()),
            "template": f.name[: -len(".xml.gz")],
            "ios": ios,
            "gateway": eng.find("GATEWAY") is not None,
            "vlan_database": eng.find("VLANS") is not None,
            "powered": eng.findtext("POWER") == "true",
            # the device's own slot tree, as pktlib walks it: not slots that
            # belong to an embedded host (the 819HG-4G-IOX's IOx computer)
            "slots": dict(sorted(collections.Counter(sl.type for sl in tree if sl.removable).items())),
            "fitted": sorted(sl.model for sl in tree if sl.removable and sl.model is not None),
        }
        if model in HOVER:
            h = HOVER[model]
            if len(h["port_names"]) != len(types):
                raise SystemExit(f"{model}: HOVER lists {len(h['port_names'])} ports, the template has {len(types)}")
            fill = cast("dict[int, str]", h.get("fill_types", {}))
            entry.update(
                h,
                verified="pt-hover",
                wired=[
                    n
                    for i, (n, t) in enumerate(zip(h["port_names"], types, strict=False))
                    if n and fill.get(i, t) in CABLE_TYPES
                ],
            )
        elif model in MANUAL:
            entry.update(MANUAL[model], verified="pt-menu")
        elif ios:
            cfg = [l.text[len("interface ") :] for l in rc if l.text and l.text.startswith("interface ")]
            cfg = [c for c in cfg if _PORT_RE.fullmatch(c) and "." not in c and not c.startswith("Vlan")]
            # only cable ports are compared: radios and cellular modems have no
            # cable menu entry. A port with no type at all can't be matched, so
            # the model stays unverified until someone reads it off the GUI.
            in_file = collections.Counter(_PREFIX[t] for t in types if t in _PREFIX and _PREFIX[t] in WIRED)
            in_cfg = collections.Counter(m[1] for c in cfg if (m := _PORT_RE.fullmatch(c)) and m[1] in WIRED)
            blank = any(not t for t in types)
            ok = not blank and in_file == in_cfg and bool(in_cfg) and entry["powered"]
            entry["wired"] = sorted((c for c in cfg if c.startswith(WIRED)), key=_order) if ok else []
            entry["verified"] = "ios-config" if ok else False
        else:
            entry["wired"], entry["verified"] = [], False
        if key in ACCEPTS:
            entry["accepts"] = ACCEPTS[key]
        spec[key] = entry
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    good = sorted(k for k, v in spec.items() if v["verified"])
    print(f"{len(spec)} models, {len(good)} verified: {', '.join(good)}")


def _order(name: str):
    from pktlib._ports import port_sort_key

    return port_sort_key(name)


if __name__ == "__main__":
    main()
