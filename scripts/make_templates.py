"""Build pktlib's bundled templates from a known-good .pkt.

    uv run python scripts/make_templates.py

Sources, all saved by Packet Tracer 8.2.0, in scripts/sources/:
  wic2t.pkt              the blank base file, and Router0 (an 1841 with a
                         WIC-2T in slot 0, factory config)
  catalogue_network.pkt  one of every network device, fresh off the palette
  catalogue_end.pkt      one of every end device (not the IoT sub-menus)
Writes src/pktlib/data/*.xml.gz: base, one template per catalogue model
(model-<model>.xml.gz), and router-1841-wic2t.
"""

from __future__ import annotations

import copy
import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pktlib._codec import decode
from pktlib._xml import req, req_attr, req_text

OUT = Path(__file__).resolve().parents[1] / "src" / "pktlib" / "data"
SRC = Path(__file__).resolve().parent / "sources"
FILES = ["wic2t.pkt", "catalogue_network.pkt", "catalogue_end.pkt", "modules.pkt"]  # modules.pkt: modules only
SOURCES = [("router-1841-wic2t", 0, "Router0")]  # (template key, which file, display name); catalogue added in main()
KEEP = "Power Distribution Device0"


def node_by_uuid(root: ET.Element, uuid: str) -> ET.Element | None:
    for n in root.iter("NODE"):
        if n.findtext("UUID_STR") == uuid:
            return n
    return None


def must_node(root: ET.Element, uuid: str) -> ET.Element:
    node = node_by_uuid(root, uuid)
    if node is None:
        raise SystemExit(f"no physical-view node {uuid}")
    return node


def slug(model: str) -> str:
    return "model-" + "".join(c if c.isalnum() or c in "-_" else "_" for c in model)


def main() -> None:
    roots = [ET.fromstring(decode((SRC / f).read_bytes())) for f in FILES]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.xml.gz"):
        if old.name != "activity.xml.gz":  # make_activity_template.py's
            old.unlink()
    sources = list(SOURCES)
    for i in (1, 2):
        for d in req(roots[i], "NETWORK/DEVICES"):
            if d.findtext("ENGINE/TYPE") != "Power Distribution Device":
                sources.append((slug(req_attr(req(d, "ENGINE/TYPE"), "model")), i, req_text(d, "ENGINE/NAME")))

    for key, i, name in sources:
        src_devices, src_pw = req(roots[i], "NETWORK/DEVICES"), req(roots[i], "PHYSICALWORKSPACE")
        dev = next(d for d in src_devices if d.findtext("ENGINE/NAME") == name)
        path = req_text(dev, "WORKSPACE/PHYSICAL").split(",")
        tpl = ET.Element("TEMPLATE", key=key, parent_type=req_text(must_node(src_pw, path[-2]), "TYPE"))
        tpl.append(copy.deepcopy(dev))
        tpl.append(copy.deepcopy(must_node(src_pw, path[-1])))
        (OUT / f"{key}.xml.gz").write_bytes(gzip.compress(ET.tostring(tpl), mtime=0))

    # every removable module in any source, first one of each model
    mods = ET.Element("MODULES")
    seen = set()
    for r in roots:
        parent_of = {c: p for p in r.iter() for c in p}
        for m in r.iter("MODULE"):
            model, kind = m.findtext("MODEL") or "", m.findtext("TYPE") or ""
            slot = parent_of.get(m)
            if not model or kind.startswith("eNonRemovable") or model in seen or slot is None or slot.tag != "SLOT":
                continue
            seen.add(model)
            entry = ET.SubElement(mods, "ENTRY", model=model, slot_type=slot.findtext("TYPE") or "")
            entry.append(copy.deepcopy(m))
    (OUT / "modules.xml.gz").write_bytes(gzip.compress(ET.tostring(mods), mtime=0))

    root = roots[0]
    devices = req(root, "NETWORK/DEVICES")
    pw = req(root, "PHYSICALWORKSPACE")
    parents = {c: p for p in pw.iter() for c in p}

    # Base file: everything except the user's devices, links, drawings and history.
    for dev in list(devices):
        if dev.findtext("ENGINE/NAME") == KEEP:
            continue
        uuid = req_text(dev, "WORKSPACE/PHYSICAL").split(",")[-1]
        node = node_by_uuid(pw, uuid)
        if node is not None:
            parents[node].remove(node)
        devices.remove(dev)
    for path in (
        "NETWORK/LINKS",
        "RECTANGLES",
        "ELLIPSES",
        "LINES",
        "POLYGONS",
        "PHYSICALWORKSPACE/NOTES",
        "COMMAND_LOGS",
    ):
        el = root.find(path)
        if el is not None:
            for c in list(el):
                el.remove(c)
    # Packet Tracer saves the paths of the files it last opened in every file: in the base
    # they'd put the template maker's Windows username and folders into every new network
    for recent in root.iter("RECENT_FILES"):
        for c in list(recent):
            recent.remove(c)
    for scen in root.iter("SCENARIO"):
        for c in list(scen):
            if c.tag != "NAME" and c.tag != "DESCRIPTION":
                scen.remove(c)
    (OUT / "base.xml.gz").write_bytes(gzip.compress(ET.tostring(root), mtime=0))
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.xml.gz"))))


if __name__ == "__main__":
    main()
