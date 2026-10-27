"""Files from before Packet Tracer 8. Found with a lecturer's 6.2 starter file
(version 6.2.0.0052) on 25 Oct 2026 and checked in Packet Tracer 8.2:
- its banners hold raw ^C bytes (0x03), which XML 1.0 forbids but PT writes;
- devices have no SAVE_REF_ID, and cables point at a device's position;
- loading and saving with pktlib gives an 8.2 file PT opens (OSPF came up);
- an 8.2 device added to its old physical workspace made PT refuse the file
  ("corrupted Physical Workspace data"), so pktlib refuses that."""

import xml.etree.ElementTree as ET

import pytest

import pktlib
from pktlib import PktError
from pktlib._codec import encode
from pktlib._xml import req, req_text


def old_file() -> bytes:
    """A small 8.2 network rewritten the way a 6.2 file looks."""
    net = pktlib.new(seed=90)
    r1, r2 = net.router("R1", "1841+WIC-2T"), net.router("R2", "1841+WIC-2T")
    r1["se0/0/0"].connect(r2["se0/0/0"])
    r1["fa0/0"].connect(net.pc("PC1")["fa0"])
    r1.config("banner motd #no Entry#")
    root = net.root
    req(root, "VERSION").text = "6.2.0.0052"
    index = {}
    for i, d in enumerate(req(root, "NETWORK/DEVICES")):
        ref = req(d, "ENGINE/SAVE_REF_ID")
        index[ref.text] = str(i)
        req(d, "ENGINE").remove(ref)
    for cable in root.iter("CABLE"):
        for tag in ("FROM", "TO", "DCEDEV"):
            el = cable.find(tag)
            if el is not None:
                el.text = index[el.text]
    for node in req(root, "PHYSICALWORKSPACE").iter("NODE"):
        for u in node.findall("UUID_STR"):
            node.remove(u)
    xml = ET.tostring(root).replace(b"banner motd #no Entry#", b"banner motd \x03no Entry\x03")
    return encode(xml)


def test_control_characters_in_banners_survive():
    net = pktlib.Network.from_bytes(old_file())
    assert "banner motd \x03no Entry\x03" in net.device("R1").running_config
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert "banner motd \x03no Entry\x03" in again.device("R1").running_config


def test_old_cable_refs_are_read_and_converted():
    net = pktlib.Network.from_bytes(old_file())
    assert sorted(l.ends for l in net.links)[0][0][0] in ("R1", "R2", "PC1")
    assert {d for l in net.links for d, _ in l.ends} == {"R1", "R2", "PC1"}
    assert req_text(net.links[0].el, "CABLE/FROM").startswith("save-ref-id:")
    serial = next(l for l in net.links if l.cable == "serial")
    assert serial.dce is not None and serial.dce[0] in ("R1", "R2")


def test_saving_an_old_file_converts_it_to_8_2():
    net = pktlib.Network.from_bytes(old_file())
    assert net.version == "6.2.0.0052" and net.edition is None
    saved = pktlib.Network.from_bytes(net.to_bytes())
    assert saved.version == "8.2.0.0162"
    assert all(d.engine.findtext("SAVE_REF_ID") for d in saved.devices)


def test_adding_devices_to_an_old_workspace_is_refused():
    net = pktlib.Network.from_bytes(old_file())
    with pytest.raises(PktError, match=r"open it in Packet Tracer 8\.2 and save it once"):
        net.pc("NEW")
    # editing what's there is fine
    net.device("R1").config("hostname EDGE")
    assert net.device("R1").hostname == "EDGE"
