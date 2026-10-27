"""Simple PDUs (one-click ping checks). PT_PDU is what Packet Tracer 8.2 saved
after Add Simple PDU from a server to a PC (26 Oct 2026), refs and colour aside."""

import xml.etree.ElementTree as ET

import pytest

import pktlib
from pktlib import PktError

PT_PDU = """<PDU><TYPE patterned="no">0</TYPE><CUSTOM_TYPE /><SOURCE>S</SOURCE><PORT /><DESTINATION device="D" />
<COLOR>C</COLOR><PDU><TYPE>CIpHeader</TYPE><SRCADDR /><DSTADDR>192.168.40.3</DSTADDR><PROTOCOL /><TTL>255</TTL>
<PDU><TYPE>CIcmpMessage</TYPE><ICMPTYPE>8</ICMPTYPE><CODE>0</CODE><ID>0</ID><SEQ>0</SEQ><CHK>0</CHK></PDU>
<TOS>0</TOS></PDU><TEST_CONDITION>0</TEST_CONDITION><POINTS>1</POINTS><PDU_SIZE>0</PDU_SIZE><START>0</START></PDU>"""


def shape(el):
    return (el.tag, dict(el.attrib) if el.tag != "DESTINATION" else {}, [shape(c) for c in el])


def two_pcs(seed):
    net = pktlib.new(seed=seed)
    a, b = net.pc("A"), net.pc("B")
    a.set_ip("192.168.40.2 255.255.255.0")
    b.set_ip("192.168.40.3 255.255.255.0")
    return net, a, b


def test_a_ping_looks_like_packet_tracers():
    net, a, b = two_pcs(111)
    net.ping("A", "B")
    pdu = net.root.find("SCENARIOSET/SCENARIO/PDU")
    assert shape(pdu) == shape(ET.fromstring(PT_PDU))
    assert pdu.findtext("SOURCE") == a.ref and pdu.find("DESTINATION").get("device") == b.ref
    assert pdu.findtext("PDU/DSTADDR") == "192.168.40.3"
    assert int(pdu.findtext("COLOR")) < 0  # opaque ARGB, signed
    assert net.pdus == [("Scenario 0", "A", "B", "192.168.40.3")]


def test_pings_survive_a_save_and_go_with_their_devices():
    net, a, b = two_pcs(112)
    net.ping(a, b)
    net.ping(b, a, scenario="Return trip")
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.pdus == [("Scenario 0", "A", "B", "192.168.40.3"), ("Return trip", "B", "A", "192.168.40.2")]
    again.remove_device("B")
    assert again.pdus == []


def test_no_address_no_ping():
    net = pktlib.new(seed=113)
    net.pc("A")
    net.pc("B")
    with pytest.raises(PktError, match="no address"):
        net.ping("A", "B")
    net.ping("A", "B", ip="10.0.0.9")
    assert net.pdus[0][3] == "10.0.0.9"


def test_profile():
    net = pktlib.new(seed=114)
    assert net.profile == ("Guest", "", "")
    net.profile = ("A Student", "a@example.com", "Lab 3")
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.profile == ("A Student", "a@example.com", "Lab 3")


def test_first_named_scenario_replaces_the_empty_default():
    # Packet Tracer opens on the first scenario; an empty "Scenario 0" ahead of
    # the named ones hid them (seen on a lab reference file, 26 Oct 2026)
    net, a, b = two_pcs(115)
    net.ping(a, b, scenario="There")
    net.ping(b, a, scenario="Back")
    assert [s.findtext("NAME") for s in net.root.iter("SCENARIO")] == ["There", "Back"]
