"""Damaged files: whatever happens to the XML, pktlib either reads it or raises a PktError.

Hypothesis takes real files (rich-answer.pkt, which Packet Tracer saved, and a network
pktlib built with one of everything), damages the XML (deletes elements and attributes, blanks or
garbles text, duplicates or reorders elements), then loads it and reads everything a user
might: devices, ports, addresses, cables, VLANs, config, drawings, ping checks, the audit,
to_python and saving. Any exception other than a PktError (an AttributeError, a ValueError
from int(), a KeyError) fails the test: that is a crash a damaged file can cause.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import PktError
from tests.conftest import FIXTURES, examples


def _built() -> bytes:
    net = pktlib.new(seed=5)
    r = net.router("R1", "1841+WIC-2T", at=(100, 100))
    r2 = net.router("R2", "2911", at=(300, 100))
    sw = net.switch("S1", at=(100, 250))
    pc = net.pc("PC1", at=(100, 400), ip="10.0.0.5/24", gateway="10.0.0.1")
    net.phone("PH1", at=(250, 400), power_adapter=True)
    pc["fa0"].connect(sw["fa0/1"])
    sw["fa0/2"].connect(r["fa0/0"])
    r2.add_module("HWIC-2T")
    r["se0/0/0"].connect(r2["se0/0/0"])
    r["fa0/0"].address = "10.0.0.1/24"
    r.config("router ospf 1\n network 10.0.0.0 0.0.0.255 area 0\ninterface se0/0/0\n clock rate 64000")
    sw.config("vlan 10\n name TEN\ninterface fa0/3\n switchport access vlan 10")
    net.ping("PC1", "R1")
    net.around("R1", "S1", label="LAN")
    net.profile = ("A Student", "a@example.com")
    r.config("ip domain-name lab.local")
    r.generate_rsa_key(1024)
    return net.to_xml()


SOURCES = {"saved": pktlib.decode((FIXTURES / "rich-answer.pkt").read_bytes()), "built": _built()}
TEXTS = st.one_of(
    st.just(""),
    st.sampled_from(["-1", "0", "nan", "inf", "1e999", "x", "?", "255.0.255.0", "10.0.0.1", "save-ref-id:1"]),
    st.text(max_size=12),
)


# what pktlib reads: damage lands here most of the time, since a file has thousands of elements
READ = set(
    """
    VERSION NETWORK DEVICES DEVICE ENGINE NAME TYPE SAVE_REF_ID SYS_NAME PORT IP SUBNET MACADDRESS
    PORT_GATEWAY GATEWAY PORT_DHCP_ENABLE IPV6_LINK_LOCAL BUILD_IN_ADDR LINKS LINK CABLE FROM TO DCEDEV DCEPORT
    WORKSPACE LOGICAL X Y DEV_ADDR PHYSICAL MODULE SLOT MODEL VLANS VLAN RUNNINGCONFIG STARTUPCONFIG
    LINE LICENSE FEATURE_NAME LICENSE_STATE SECURITY ENABLED MODULUS_BITS KEY_NAME SCENARIOSET
    SCENARIO PDU SOURCE DESTINATION DSTADDR RECTANGLES RECTANGLE ELLIPSES ELLIPSE TopLeftX
    BottomRightY Filled Color Red NOTES NOTE TEXT USER_PROFILE EMAIL PHYSICALWORKSPACE NODE UUID_STR
    CHILDREN
    """.split()  # noqa: SIM905  (a word list reads better than 70 quoted strings)
)


def _damage(root: ET.Element, data: st.DataObject) -> None:
    for _ in range(data.draw(st.integers(1, 6))):
        els = list(root.iter())
        read = [e for e in els if e.tag in READ]
        el = data.draw(st.sampled_from(read if read and data.draw(st.integers(0, 9)) else els))
        how = data.draw(st.sampled_from(["delete", "text", "attr", "dup", "clear", "move"]))
        parents = {c: p for p in root.iter() for c in p}
        if how == "delete" and el in parents:
            parents[el].remove(el)
        elif how == "text":
            el.text = data.draw(TEXTS)
        elif how == "attr" and el.attrib:
            key = data.draw(st.sampled_from(sorted(el.attrib)))
            if data.draw(st.booleans()):
                del el.attrib[key]
            else:
                el.attrib[key] = data.draw(TEXTS)
        elif how == "dup" and el in parents:
            parents[el].append(copy.deepcopy(el))
        elif how == "clear":
            for c in list(el):
                el.remove(c)
        elif how == "move" and el in parents and len(parents[el]) > 1:
            p = parents[el]
            p.remove(el)
            p.insert(data.draw(st.integers(0, len(p))), el)


def _read_everything(net: pktlib.Network) -> None:
    repr(net)
    _ = net.version, net.edition, net.profile, net.pdus, net.shapes, net.notes
    for s in net.shapes:
        _ = s.box, s.outline, s.fill, repr(s)
    for n in net.notes:
        _ = n.text, n.xy
    for d in net:
        _ = d.name, d.kind, d.model, d.xy, d.hostname, d.has_ios, d.slots, d.modules, d.vlans, d.licenses
        _ = d.interfaces, d.rsa_key, d.dhcp, d.gateway, repr(d)
        for p in d:
            _ = p.name, p.type, p.mac, p.ip, p.mask, p.up, p.address, p.link, p.module
            _ = p.mode, p.access_vlan, p.peer
    for link in net.links:
        _ = link.ends, link.ports, link.cable, link.dce, repr(link)
    pktlib.audit(net)
    pktlib.to_python(net)
    net.to_bytes()


@pytest.mark.parametrize("source", sorted(SOURCES))
@settings(
    max_examples=examples(40),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(data=st.data())
def test_damaged_files_read_or_raise_a_pkt_error(source, data):
    root = ET.fromstring(SOURCES[source])
    _damage(root, data)
    try:
        net = pktlib.Network.from_xml(ET.tostring(root), strict=data.draw(st.booleans()))
        _read_everything(net)
    except PktError:
        pass
