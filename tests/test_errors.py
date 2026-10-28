"""The exception classes, and refusals that must leave the network as it was."""

import subprocess
import sys

import pytest

import pktlib
import pktlib._modules
from pktlib import FileFormatError, NotFound, PktError, TagMismatch


def test_hierarchy():
    assert issubclass(NotFound, PktError) and issubclass(NotFound, KeyError)
    assert issubclass(FileFormatError, PktError) and issubclass(TagMismatch, FileFormatError)
    assert issubclass(PktError, ValueError)


def test_not_found_reads_like_a_message_not_a_key(net):
    r = net.router("R1", "2911")
    with pytest.raises(NotFound) as e:
        r["fa9/9"]
    assert str(e.value).startswith("R1 has no port FastEthernet9/9")  # KeyError would quote it


@pytest.mark.parametrize(
    "lookup",
    [
        lambda n: n.device("R9"),
        lambda n: n.device("R1")["g9/9"],
        lambda n: n.device("R1").remove_module((9,)),
        lambda n: n.device("S1").remove_vlan(77),
        lambda n: n.device("R1").enable_license("nosuchk9"),
        lambda n: n.add_device("X", "9999"),
        lambda n: pktlib._modules.fresh_module("NO-SUCH-CARD"),
        lambda n: n.disconnect("R1", "g0/0"),
    ],
)
def test_failed_lookups_are_key_errors(net, lookup):
    net.router("R1", "2911")
    net.switch("S1")
    with pytest.raises(KeyError):
        lookup(net)


@pytest.mark.parametrize("data", [b"", b"garbage", b"\x00" * 64])
def test_unreadable_bytes_are_file_format_errors(data):
    with pytest.raises(FileFormatError):
        pktlib.Network.from_bytes(data)


def test_bad_xml_is_a_file_format_error():
    with pytest.raises(FileFormatError, match="not well-formed"):
        pktlib.Network.from_xml("<nope")
    with pytest.raises(FileFormatError, match="not Packet Tracer XML"):
        pktlib.Network.from_xml("<other/>")


def test_missing_element_names_what_is_missing(net):
    r = net.router("R1", "2911")
    r.el.remove(r.el.find("ENGINE"))
    with pytest.raises(FileFormatError, match="no <ENGINE> under <DEVICE>"):
        r.name  # noqa: B018


def test_wrong_types_are_type_errors(net):
    r = net.router("R1", "2911")
    with pytest.raises(TypeError):
        r[0]
    with pytest.raises(TypeError):
        net.add_device(42, "2911")
    with pytest.raises(TypeError):
        r.xy = "here"


# --- renames: the checks add_device makes ------------------------------------------


def test_rename_refuses_a_taken_name(net):
    r = net.router("R1", "2911")
    net.switch("S1")
    with pytest.raises(PktError, match="already a device called 'S1'"):
        r.name = "S1"
    assert [d.name for d in net.devices] == ["R1", "S1"]


@pytest.mark.parametrize("bad", ["", "1R", "has space", "x" * 65, "R1!"])
def test_rename_refuses_a_bad_name(net, bad):
    r = net.router("R1", "2911")
    with pytest.raises(PktError, match="bad device name"):
        r.name = bad
    assert r.name == "R1"


def test_rename_to_itself_is_fine(net):
    r = net.router("R1", "2911")
    r.name = "R1"
    assert r.name == "R1"


# --- refusals leave no trace --------------------------------------------------


@pytest.mark.parametrize("at", [("a", "b"), (1,), (float("nan"), 0), (0, float("inf")), (True, 0), "here"])
def test_a_bad_position_adds_nothing(net, at):
    before = net.to_xml()
    with pytest.raises((TypeError, PktError)):
        net.pc("P2", at=at)
    assert "P2" not in net
    assert net.to_xml() == before


def test_a_bad_position_moves_nothing(net):
    r = net.router("R1", "2911", at=(10, 20))
    with pytest.raises(PktError, match="finite"):
        r.xy = (float("nan"), 0)
    assert r.xy == (10, 20)


def test_cli_reports_errors_without_a_traceback(tmp_path):
    bad = tmp_path / "bad.pkt"
    bad.write_bytes(b"not a pkt at all")
    run = subprocess.run([sys.executable, "-m", "pktlib", "info", str(bad)], capture_output=True, text=True)
    assert run.returncode == 1
    assert run.stderr.startswith("pktlib: ") and "Traceback" not in run.stderr


# --- nothing that can't be saved gets in -----------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda n: n.device("S1").add_vlan(10, 5),
        lambda n: n.ping("PC1", "R1", ip=5),
        lambda n: n.ping("PC1", "R1", ip="10.0.0.1", scenario=5),
        lambda n: setattr(n, "profile", 5),
        lambda n: n.device("R1").config(["hostname A", None]),
        lambda n: n.device("R1").config(None),
        lambda n: n.device("R1").generate_rsa_key("1024"),
        lambda n: n.device("S1").remove_vlan("10"),
        lambda n: n.device("R1").add_module("HWIC-2T", slot=1),
        lambda n: n.note(5, at=(0, 0)),
        lambda n: pktlib.new(edition=8.2),  # ty: ignore[invalid-argument-type]
    ],
)
def test_wrong_types_never_reach_the_file(net, call):
    net.router("R1", "2911")
    net.switch("S1")
    net.pc("PC1", ip="10.0.0.5/24")
    before = net.to_xml()
    with pytest.raises(TypeError):
        call(net)
    assert net.to_xml() == before


@pytest.mark.parametrize(
    "call",
    [
        lambda n: n.pc("P2", ip="10.0.0.1"),
        lambda n: n.pc("P2", ip="300.1.1.1/24"),
        lambda n: n.pc("P2", ip="10.0.0.5/24", gateway="10.0.1.1"),
        lambda n: n.pc("P2", gateway="10.0.0.1"),
        lambda n: n.device("S1").config("vlan 30\n name X\nvlan 99999"),
        lambda n: n.device("S1").config("vlan 30\nvlan 20-x"),
        lambda n: n.around("R1", label="   "),
        lambda n: n.device("R1").config("interface g0/1\n ip address 10.0.0.1/24"),
        lambda n: n.device("R1").config("interface g0/1\n ip address 10.0.0.1 255.0.255.0"),
        lambda n: n.ping("PC1", "R1", ip="nope"),
        lambda n: n.rectangle(0, 0, 0.4, 0.4),
        lambda n: n.device("PC1").set_ip("10.0.0.1"),
    ],
)
def test_refusals_leave_the_network_as_it_was(net, call):
    net.router("R1", "2911")
    net.switch("S1")
    net.pc("PC1", ip="10.0.0.5/24")
    before = net.to_xml()
    with pytest.raises(PktError):
        call(net)
    assert net.to_xml() == before


# --- config is written the way IOS saves it ------------------------------------


def test_tabs_mode_lines_and_embedded_newlines(net):
    r = net.router("R1", "2911")
    r.config("conf t\nrouter ospf 1\n\tnetwork 10.0.0.0 0.0.0.255 area 0\n exit\nend")
    r.config(["hostname EDGE\nip domain-name lab.local"])
    rc = r.running_config
    i = rc.index("router ospf 1")
    assert rc[i + 1] == " network 10.0.0.0 0.0.0.255 area 0"
    assert not any(line.strip() in ("exit", "conf t") for line in rc)
    assert "hostname EDGE" in rc and "ip domain-name lab.local" in rc


def test_an_exit_line_does_not_split_an_interface(net):
    """With ` exit` kept, a later address landed after it: global config on replay."""
    r = net.router("R1", "2911")
    r.config("interface g0/1\n description uplink\n exit")
    r.config("interface g0/1\n ip address 10.0.0.1 255.255.255.0\n no shutdown")
    assert r["g0/1"].address == "10.0.0.1/24" and r["g0/1"].up
    i = r.running_config.index("interface GigabitEthernet0/1")
    assert "exit" not in [line.strip() for line in r.running_config[i : i + 6]]


def test_inconsistent_indent_is_refused(net):
    r = net.router("R1", "2911")
    with pytest.raises(PktError, match="starts indented"):
        r.config("  router ospf 1\n network 10.0.0.0 0.0.0.255 area 0")


def test_no_vlan_takes_it_out_of_the_database(net):
    s = net.switch("S1")
    s.config("vlan 10\n name TEN")
    s.config("no vlan 10")
    assert 10 not in s.vlans
    assert not any("vlan 10" in line for line in s.running_config)


@pytest.mark.parametrize("line", ["SWITCHPORT ACCESS VLAN 77", "sw acc vlan 77", "switchport voice vl 77"])
def test_shorthand_switchport_vlan_creates_it(net, line):
    s = net.switch("S1")
    s.config(f"interface fa0/1\n {line}")
    assert 77 in s.vlans


def test_removing_a_vlan_in_use_warns(net):
    s = net.switch("S1")
    s.config("interface fa0/5\n switchport access vlan 40")
    with pytest.warns(pktlib.PktWarning, match="FastEthernet0/5 still use it"):
        s.remove_vlan(40)


# --- end devices ----------------------------------------------------------------


def test_set_ip_takes_a_prefix_as_text_and_turns_dhcp_off(net):
    pc = net.pc("PC1")
    pc.use_dhcp()
    pc.set_ip("10.0.0.5 255.255.255.0", "10.0.0.1")
    assert pc["fa0"].address == "10.0.0.5/24" and not pc.dhcp


def test_set_ip_on_ios_points_at_the_port_address(net):
    r = net.router("R1", "2911")
    with pytest.raises(PktError, match=r"runs IOS: set r\['g0/0'\]\.address"):
        r.set_ip("10.0.0.1/24", port="g0/0")


def test_ping_skips_ports_that_are_down(net):
    r = net.router("R1", "2911")
    r.config("interface g0/0\n ip address 10.0.0.1 255.255.255.0\n shutdown")
    r["g0/1"].address = "10.0.1.1/24"
    net.pc("PC1", ip="10.0.1.5/24")
    net.ping("PC1", "R1")
    assert net.pdus[-1][3] == "10.0.1.1"


def test_an_empty_cable_name_is_not_auto(net):
    a, b = net.pc("A"), net.pc("B")
    with pytest.raises(PktError, match="unknown cable ''"):
        a["fa0"].connect(b["fa0"], cable="")  # type: ignore[arg-type]


# --- messages that say what to do -----------------------------------------------


def test_model_names_ignore_case_and_near_misses_get_a_suggestion(net):
    assert net.add_device("A", "isr4331").model == "ISR4331"
    with pytest.raises(NotFound, match="did you mean"):
        net.add_device("B", "ISR4332")


def test_a_module_packet_tracer_takes_but_pktlib_lacks(net):
    r = net.router("R1", "2911")
    with pytest.raises(PktError, match="no template for HWIC-8A"):
        r.add_module("HWIC-8A")


def test_not_a_port_name_is_not_found(net):
    r = net.router("R1", "2911")
    with pytest.raises(NotFound, match="no port 'foo'"):
        r["foo"]


def test_big_coordinates_have_no_exponent(net):
    r = net.router("R1", "2911")
    r.xy = (1234567.8, 0)
    assert r.el.findtext("WORKSPACE/LOGICAL/X") == "1234567.8"


@pytest.mark.parametrize(
    "damage,expect",
    [
        (lambda b: b[:200], "not a .pkt Packet Tracer saved, or damaged"),
        (lambda b: b"", "too short"),
    ],
)
def test_cli_names_the_file_and_says_what_is_wrong(tmp_path, routed_bytes, damage, expect):
    bad = tmp_path / "lab.pkt"
    bad.write_bytes(damage(routed_bytes))
    run = subprocess.run([sys.executable, "-m", "pktlib", "info", str(bad)], capture_output=True, text=True)
    assert run.returncode == 1 and f"{bad}: " in run.stderr and expect in run.stderr


def test_cli_encode_refuses_xml_packet_tracer_could_not_open(tmp_path):
    src = tmp_path / "bad.xml"
    src.write_text("<PACKETTRACER5><unclosed>")
    run = subprocess.run(
        [sys.executable, "-m", "pktlib", "encode", str(src), str(tmp_path / "x.pkt")], capture_output=True, text=True
    )
    assert run.returncode == 1 and "not well-formed" in run.stderr and not (tmp_path / "x.pkt").exists()


@pytest.mark.parametrize("tag,value", [("X", ""), ("Y", "nan"), ("X", "1e999")])
def test_a_damaged_note_position_is_a_file_format_error(net, tag, value):
    """Found by tests/test_fuzz_files.py: a blank <X> under a note raised float()'s ValueError."""
    note = net.note("hi", at=(1, 2))
    note.el.find(tag).text = value
    with pytest.raises(FileFormatError, match=f"<{tag}> under <NOTE>"):
        note.xy  # noqa: B018


def test_a_damaged_shape_colour_is_a_file_format_error(net):
    shape = net.rectangle(0, 0, 10, 10, fill="red")
    shape.el.find("Color/Red").text = "300"
    with pytest.raises(FileFormatError, match="0-255"):
        shape.fill  # noqa: B018


def test_config_for_a_port_the_device_lacks_is_refused_and_renames_nothing(net):
    """Found by tests/test_properties.py: an ISR4331's port names come from its config, so
    `interface g0/0` (it has Gi0/0/0-2) renamed its ports and left a cable on Gi0/0/2
    pointing at nothing."""
    r = net.add_device("R", "ISR4331")
    pc = net.pc("PC1")
    r["g0/0/2"].connect(pc["fa0"])
    before = net.to_xml()
    with pytest.raises(PktError, match=r"R has no interface GigabitEthernet0/0;"):
        r.config("interface g0/0\n shutdown")
    with pytest.raises(PktError, match=r"no interface GigabitEthernet0/9 \(for GigabitEthernet0/9\.10\)"):
        r.config("interface g0/9.10\n encapsulation dot1q 10")
    assert net.to_xml() == before
    assert list(r.ports) == ["GigabitEthernet0/0/0", "GigabitEthernet0/0/1", "GigabitEthernet0/0/2"]
    r.config("interface g0/0/1.10\n encapsulation dot1Q 10\ninterface loopback0\ninterface vlan1")


@pytest.mark.parametrize("line", ["interface", "router", "line"])
def test_a_block_header_alone_is_refused(net, line):
    with pytest.raises(PktError, match="needs"):
        net.router("R1", "2911").config(line)


def test_audit_reports_a_pc_address_that_is_not_ipv4(net):
    """Found by the damaged-file fuzzer: a PC port whose IP text is '-1' crashed the audit."""
    pc = net.pc("PC1", ip="10.0.0.5/24")
    pc["fa0"].el.find("IP").text = "-1"
    assert any("PC1.FastEthernet0: -1/24 isn't an IPv4 address" in p for p in pktlib.audit(net))


# Things Packet Tracer 8.2 drops without a word (round 1 checks, 26 Oct 2026):
# pktlib refuses them, so a file never says something Packet Tracer won't do.


def test_a_vlan_name_already_in_use_is_refused(net):
    """Check 3: VLAN 60 'SAME' beside VLAN 50 'SAME' was gone from the re-save."""
    sw = net.switch("S1", "2960-24TT")
    sw.add_vlan(50, "SAME")
    with pytest.raises(pktlib.PktError, match="already named 'SAME'"):
        sw.add_vlan(60, "SAME")
    with pytest.raises(pktlib.PktError, match="already named 'SAME'"):
        sw.config("vlan 60\n name SAME")
    with pytest.raises(pktlib.PktError, match="already named"):
        sw.config("vlan 70-71\n name BOTH")  # one name for a range names every VLAN in it
    assert 60 not in sw.vlans and 70 not in sw.vlans
    sw.add_vlan(50, "SAME")  # renaming a VLAN to its own name is fine
    sw.config("no vlan 50\nvlan 60\n name SAME")  # and so is reusing a name being freed
    assert sw.vlans[60] == "SAME"


def test_a_cable_between_two_ports_of_one_device_is_refused(net):
    """Check 8: Packet Tracer dropped SW1 Fa0/1 to Fa0/2 on load."""
    sw = net.switch("S1", "2960-24TT")
    with pytest.raises(pktlib.PktError, match="two ports of one device"):
        sw["fa0/1"].connect(sw["fa0/2"])
    assert not net.links


def test_config_on_a_7960_phone_is_refused(net):
    """Check 11: the phone's `hostname` was gone from the re-save; it has no CLI."""
    with pytest.raises(pktlib.PktError, match="no CLI"):
        net.phone("PH1").config("hostname X")


def test_an_address_on_bluetooth_is_refused(net):
    """Check 14: IP Configuration lists no Bluetooth, and its Config page has no IP fields."""
    lt = net.laptop("LT1")
    with pytest.raises(pktlib.PktError, match="Bluetooth"):
        lt.set_ip("10.0.0.5/24", port="Bluetooth")
    lt.set_ip("10.0.0.5/24", port="FastEthernet0")


def test_a_2960_port_address_warns(net):
    """Check 7: `no switchport` and `ip address` on a 2960's Fa0/1 were both dropped."""
    sw = net.switch("S1", "2960-24TT")
    with pytest.warns(pktlib.PktWarning, match="switch ports only") as caught:
        sw.config("interface fa0/1\n no switchport\n ip address 10.0.0.1 255.255.255.0")
    assert len(caught) == 2
    assert any("switch ports only" in str(p) for p in pktlib.audit(net))
    sw.config("interface Vlan1\n ip address 10.0.0.2 255.255.255.0")  # the SVI is where it goes
