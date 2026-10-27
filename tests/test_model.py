"""The object model: reading a known-good file, building, editing, and refusing nonsense."""

import gzip
import itertools
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import PktError
from pktlib._codec import decode
from pktlib._xml import req
from tests.conftest import examples

ROUTED_LINKS = {
    (("R1", "Serial0/0/0"), ("R2", "Serial0/0/0"), "serial"),
    (("R2", "Serial0/0/1"), ("R3", "Serial0/0/0"), "serial"),
    (("R2", "FastEthernet0/0"), ("R4", "FastEthernet0/0"), "cross"),
    (("R1", "FastEthernet0/0"), ("S1", "FastEthernet0/1"), "straight"),
    (("S1", "FastEthernet0/2"), ("PC1", "FastEthernet0"), "straight"),
    (("R3", "FastEthernet0/0"), ("S3", "FastEthernet0/1"), "straight"),
    (("S3", "FastEthernet0/2"), ("PC3", "FastEthernet0"), "straight"),
    (("R4", "FastEthernet0/1"), ("PC4", "FastEthernet0"), "cross"),
}


# --- reading a routed network (scripts/sources/routed.py) ---------------------


def test_routed_devices(routed):
    got = {(d.name, d.kind, d.model) for d in routed.devices}
    assert got == {
        ("R1", "Router", "1841"),
        ("R2", "Router", "1841"),
        ("R3", "Router", "1841"),
        ("R4", "Router", "1841"),
        ("PC1", "Pc", "PC-PT"),
        ("PC3", "Pc", "PC-PT"),
        ("PC4", "Pc", "PC-PT"),
        ("S1", "Switch", "2960-24TT"),
        ("S3", "Switch", "2960-24TT"),
    }
    assert routed.version == "8.2.0.0162"


def test_routed_links(routed):
    assert {(*l.ends, l.cable) for l in routed.links} == ROUTED_LINKS


def test_routed_dce_ends(routed):
    assert {l.dce for l in routed.links if l.cable == "serial"} == {("R1", "Serial0/0/0"), ("R2", "Serial0/0/1")}


@pytest.mark.parametrize(
    "dev,port,addr",
    [
        ("R1", "fa0/0", "10.1.0.1/24"),
        ("R1", "se0/0/0", "10.0.12.1/30"),
        ("R2", "s0/0/1", "10.0.23.1/30"),
        ("R3", "Serial0/0/0", "10.0.23.2/30"),
        ("R2", "fa0/0", "10.0.24.1/30"),
        ("R3", "fa0/0", "10.3.0.1/24"),
        ("R4", "fa0/1", "10.4.0.1/24"),
        ("PC1", "fa0", "10.1.0.10/24"),
        ("PC4", "FastEthernet0", "10.4.0.10/24"),
    ],
)
def test_routed_addresses(routed, dev, port, addr):
    assert routed.device(dev)[port].address == addr


def test_routed_pc_gateways(routed):
    assert [routed.device(p).gateway for p in ("PC1", "PC3", "PC4")] == ["10.1.0.1", "10.3.0.1", "10.4.0.1"]


def test_routed_unconfigured_ports(routed):
    p = routed.device("R1")["fa0/1"]
    assert p.address is None and not p.up and p.link is None


def test_routed_ports_and_names(routed):
    assert list(routed.device("R1").ports) == ["FastEthernet0/0", "FastEthernet0/1", "Serial0/0/0", "Serial0/0/1"]
    assert list(routed.device("R4").ports) == ["FastEthernet0/0", "FastEthernet0/1"]
    assert list(routed.device("PC1").ports) == ["FastEthernet0", "Bluetooth"]
    assert len(routed.device("S1").ports) == 26


def test_routed_hostnames(routed):
    assert routed.device("R3").hostname == "R3"
    assert routed.device("S1").hostname == "S1"


def test_routed_clock_rate(routed):
    assert routed.device("R1").interface_config("se0/0/0")["clock rate"] == "clock rate 64000"


def test_routed_drawings(routed):
    assert sorted(s.kind for s in routed.shapes) == ["ellipse", "ellipse", "rectangle"]
    assert {n.text for n in routed.notes} == {"RIP v2", "LAN 1 10.1.0.0/24", "LAN 3 10.3.0.0/24"}


def test_routed_no_duplicate_macs(routed):
    assert routed.duplicate_macs() == {}


def test_lookup_errors(routed):
    with pytest.raises(PktError, match="no device"):
        routed.device("R9")
    with pytest.raises(PktError, match="has no port"):
        routed.device("R4")["se0/0/0"]
    assert "R1" in routed and "R9" not in routed


# --- save / load ------------------------------------------------------------------


def test_save_and_reload_is_identical(routed, tmp_path):
    p = tmp_path / "x.pkt"
    routed.save(p)
    again = pktlib.load(p)
    assert again.to_xml() == routed.to_xml()


def test_not_packet_tracer_xml():
    with pytest.raises(PktError):
        pktlib.Network.from_xml(b"<html/>")


def test_seed_makes_builds_reproducible():
    def build():
        n = pktlib.new(seed=42)
        r = n.router("R1", "2911")
        s = n.switch("S1")
        r["g0/0"].connect(s["fa0/1"])
        return n.to_xml()

    assert build() == build()


# --- building -----------------------------------------------------------------------


def test_new_is_empty(net):
    assert net.devices == [] and net.links == [] and net.shapes == [] and net.notes == []


def test_every_verified_model_can_be_added_saved_and_reloaded(net, spec, tmp_path):
    models = [m for m, s in spec.items() if s["verified"]]
    for i, m in enumerate(models):
        net.add_device(f"D{i}", m, at=(100 + i * 10, 100))
    net.save(tmp_path / "all.pkt")
    again = pktlib.load(tmp_path / "all.pkt")
    assert [(d.name, d.model) for d in again.devices] == [
        (f"D{i}", spec[m].get("model", m).replace("1841+WIC-2T", "1841")) for i, m in enumerate(models)
    ]
    assert again.duplicate_macs() == {}


@pytest.mark.parametrize("model", ["2911", "ISR4331", "1841", "1841+WIC-2T", "2960-24TT", "3560-24PS", "3650-24PS"])
def test_new_ios_device_has_its_hostname(net, model):
    d = net.add_device("Edge-1", model)
    assert d.hostname == "Edge-1"
    assert d.engine.findtext("SYS_NAME") == "Edge-1"


def test_aliases(net):
    assert net.add_device("A", "2960").model == "2960-24TT"
    assert net.add_device("B", "4331").model == "ISR4331"
    assert net.add_device("C", "pc").model == "PC-PT"


@pytest.mark.parametrize("bad", ["", "1x", "has space", "a.b", "x" * 65, "-lead"])
def test_bad_names(net, bad):
    with pytest.raises(PktError):
        net.add_device(bad, "2911")


@pytest.mark.parametrize("bad", [None, 5])
def test_names_are_strings(net, bad):
    with pytest.raises(TypeError):
        net.add_device(bad, "2911")


def test_duplicate_name(net):
    net.router("R1")
    with pytest.raises(PktError, match="already"):
        net.switch("R1")


def test_unknown_and_unverified_models(net, monkeypatch):
    # every 8.2 model is verified now; a later edition's new ones won't be at first
    from pktlib._model import SPEC

    monkeypatch.setitem(SPEC, "Meraki-MX65W", {**SPEC["Meraki-MX65W"], "verified": False})
    with pytest.raises(PktError, match="unknown model"):
        net.add_device("X", "9999")
    with pytest.raises(PktError, match="verified"):
        net.add_device("X", "Meraki-MX65W")
    assert net.add_device("X", "Meraki-MX65W", unverified=True).model == "Meraki-MX65W"
    with pytest.raises(TypeError, match="string like '2911'"):
        net.add_device("Y", 2911)


def test_fresh_devices_get_unique_ids_and_macs(net):
    devs = [net.add_device(f"S{i}", "3650-24PS") for i in range(5)] + [net.phone(f"P{i}") for i in range(5)]
    assert len({d.ref for d in devs}) == 10
    assert len({d.uuid for d in devs}) == 10
    assert net.duplicate_macs() == {}


def test_physical_view_node_added_and_removed(net):
    d = net.router("R1")
    assert net._physical_node(d.uuid) is not None
    net.remove_device("R1")
    assert net._physical_node(d.uuid) is None and "R1" not in net


def test_rename_updates_the_physical_view(net):
    d = net.router("R1")
    d.name = "Edge"
    assert net._physical_node(d.uuid).findtext("NAME") == "Edge"
    assert net.device("Edge")


def test_positions(net):
    d = net.pc("P", at=(12.5, 300))
    assert d.xy == (12.5, 300.0)
    d.xy = (7, 8)
    assert d.xy == (7.0, 8.0)


# --- cabling -------------------------------------------------------------------------


@pytest.fixture
def lab(net):
    net.router("R1", "1841+WIC-2T")
    net.router("R2", "1841+WIC-2T")
    net.router("G", "2911")
    net.switch("S1")
    net.switch("S2")
    net.multilayer("M")
    net.pc("P")
    net.server("SRV")
    net.phone("PH")
    return net


@pytest.mark.parametrize(
    "a,ap,b,bp,want",
    [
        ("R1", "fa0/0", "S1", "fa0/1", "straight"),
        ("S1", "fa0/2", "P", "fa0", "straight"),
        ("R1", "fa0/0", "R2", "fa0/0", "cross"),
        ("R1", "fa0/0", "P", "fa0", "cross"),
        ("S1", "g0/1", "S2", "g0/1", "cross"),
        ("M", "fa0/1", "S1", "fa0/1", "cross"),
        ("G", "g0/0", "M", "g0/1", "straight"),
        ("R1", "se0/0/0", "R2", "se0/0/1", "serial"),
        ("S1", "fa0/3", "PH", "Switch", "straight"),
        ("PH", "PC", "P", "fa0", "straight"),
    ],
)
def test_auto_cable(lab, a, ap, b, bp, want):
    link = lab.connect(a, ap, b, bp)
    assert link.cable == want
    assert link.ends == ((a, lab.device(a).port(ap).name), (b, lab.device(b).port(bp).name))


def test_serial_dce_is_the_first_port(lab):
    l = lab.device("R2")["se0/0/1"].connect(lab.device("R1")["se0/0/0"])
    assert l.dce == ("R2", "Serial0/0/1")


def test_forced_cable(lab):
    assert lab.connect("R1", "fa0/0", "S1", "fa0/1", cable="cross").cable == "cross"


@pytest.mark.parametrize(
    "a,ap,b,bp,cable,msg",
    [
        ("R1", "se0/0/0", "S1", "fa0/1", None, "serial only joins serial"),
        ("R1", "fa0/0", "R1", "fa0/0", None, "itself"),
        ("P", "Bluetooth", "S1", "fa0/1", None, "Bluetooth"),
        ("R1", "fa0/0", "S1", "fa0/1", "fibre", "unknown cable"),
        ("R1", "fa0/0", "S1", "fa0/1", "serial", "doesn't fit"),
        ("R1", "fa0/9", "S1", "fa0/1", None, "has no port"),
        ("NOPE", "fa0/0", "S1", "fa0/1", None, "no device"),
    ],
)
def test_bad_cables(lab, a, ap, b, bp, cable, msg):
    with pytest.raises(PktError, match=msg):
        lab.connect(a, ap, b, bp, cable)


def test_port_in_use(lab):
    lab.connect("R1", "fa0/0", "S1", "fa0/1")
    with pytest.raises(PktError, match="already has a cable"):
        lab.connect("S1", "fa0/1", "P", "fa0")


def test_disconnect(lab):
    lab.connect("R1", "fa0/0", "S1", "fa0/1")
    lab.device("S1")["fa0/1"].disconnect()
    assert lab.links == []
    with pytest.raises(PktError, match="no cable"):
        lab.disconnect("S1", "fa0/1")


def test_remove_device_takes_its_cables(lab):
    lab.connect("R1", "fa0/0", "S1", "fa0/1")
    lab.connect("S1", "fa0/2", "P", "fa0")
    lab.remove_device("S1")
    assert lab.links == []


def test_connect_rejects_non_ports(lab):
    with pytest.raises(TypeError, match="wants a Port"):
        lab.device("R1")["fa0/0"].connect("S1")
    other = pktlib.new(seed=2)
    x = other.switch("X")
    with pytest.raises(PktError, match="different networks"):
        lab.device("R1")["fa0/0"].connect(x["fa0/1"])


# --- addressing and config ---------------------------------------------------------------


def test_router_address_goes_into_config(net):
    r = net.router("R1", "2911")
    r["g0/0"].address = "10.0.0.1/30"
    assert r["g0/0"].address == "10.0.0.1/30" and r["g0/0"].up
    assert "interface GigabitEthernet0/0" in r.running_config
    assert r.running_config == r._config("STARTUPCONFIG")


def test_pc_address_goes_into_the_port(net):
    p = net.pc("P", ip="10.1.1.10/24", gateway="10.1.1.1")
    assert p["fa0"].address == "10.1.1.10/24" and p.gateway == "10.1.1.1"
    p["fa0"].address = "10.1.1.11/24"
    assert p["fa0"].address == "10.1.1.11/24" and p.gateway == "10.1.1.1"


@pytest.mark.parametrize(
    "ip,gw,msg",
    [
        ("10.0.0.1/33", "", "not a valid netmask"),
        ("10.0.0.256/24", "", "Octet 256"),
        ("10.0.0.1", "", "needs a mask"),
        ("10.0.0.1/24", "10.0.1.1", "outside"),
        ("10.0.0.1/24", "nope", "IPv4"),
    ],
)
def test_bad_pc_addresses(net, ip, gw, msg):
    with pytest.raises(PktError, match=msg):
        net.pc("P", ip=ip, gateway=gw)


def test_gateway_without_ip(net):
    with pytest.raises(PktError):
        net.pc("P", gateway="10.0.0.1")


def test_dhcp(net):
    p = net.pc("P", ip="10.0.0.5/24", gateway="10.0.0.1")
    p.use_dhcp()
    assert p.dhcp and p["fa0"].address is None and p.gateway == ""
    with pytest.raises(PktError):
        net.router("R").use_dhcp()


def test_config_dedents_and_goes_before_end(net):
    r = net.router("R1", "2911")
    r.config("""
        router ospf 1
         network 10.0.0.0 0.0.0.255 area 0
    """)
    cfg = r.running_config
    assert cfg[-1] == "end"
    i = cfg.index("router ospf 1")
    assert cfg[i + 1] == " network 10.0.0.0 0.0.0.255 area 0" and i < cfg.index("end")


def test_interface_range_is_expanded_when_written(net):
    s = net.switch("S1")
    s.config("interface range fa0/1 - 3\n switchport mode access")
    cfg = s.running_config
    assert not any("range" in l for l in cfg)
    assert all(s.interface_config(f"fa0/{i}")["switchport mode"] == "switchport mode access" for i in (1, 2, 3))


def test_vlans_go_to_the_vlan_database(net):
    s = net.switch("S1")
    s.config("vlan 10\n name SALES\nvlan 20,30\ninterface fa0/1\n switchport access vlan 40")
    assert {10: "SALES", 20: "VLAN0020", 30: "VLAN0030", 40: "VLAN0040"}.items() <= s.vlans.items()
    assert not any(l.startswith("vlan ") for l in s.running_config)
    s.remove_vlan(30)
    assert 30 not in s.vlans
    for bad in (1, 1002, 999):
        with pytest.raises(PktError):
            s.remove_vlan(bad)
    for bad in (0, 4095):
        with pytest.raises(PktError):
            s.add_vlan(bad)
    for wrong in (True, "10", 10.0):
        with pytest.raises(TypeError):
            s.add_vlan(wrong)


def test_routers_keep_vlan_lines_in_config(net):
    r = net.router("R1", "2911")
    r.config("vlan 10")
    assert "vlan 10" in r.running_config


def test_subinterfaces_and_svis_are_read(net):
    r = net.router("R1", "2911")
    r.config("interface g0/0.10\n encapsulation dot1Q 10\n ip address 10.0.10.1 255.255.255.0")
    m = net.multilayer("M")
    m.config("interface vlan 20\n ip address 10.0.20.1 255.255.255.0\n no shutdown")
    assert r.interfaces["GigabitEthernet0/0.10"] == ("10.0.10.1/24", True)
    assert m.interfaces["Vlan20"] == ("10.0.20.1/24", True)


def test_pc_has_no_ios(net):
    p = net.pc("P")
    assert not p.has_ios and p.running_config == [] and p.interfaces == {}
    with pytest.raises(PktError):
        p.config("hostname x")


# --- fuzzing whole builds ------------------------------------------------------------------

MODELS = ["2911", "1841+WIC-2T", "2960-24TT", "3560-24PS", "PC-PT", "Server-PT", "7960"]


@settings(max_examples=examples(15), deadline=None)
@given(st.lists(st.sampled_from(MODELS), min_size=2, max_size=7), st.data())
def test_fuzz_random_networks_survive_save_and_load(models, data):
    net = pktlib.new(seed=data.draw(st.integers(0, 10**6)))
    devs = [net.add_device(f"D{i}", m, at=(i * 50, 100)) for i, m in enumerate(models)]
    made = 0
    for a, b in itertools.combinations(devs, 2):
        if not data.draw(st.booleans()):
            continue
        free_a = [p for p in a.ports.values() if p.link is None and p.type != "eBluetooth"]
        free_b = [p for p in b.ports.values() if p.link is None and p.type != "eBluetooth"]
        pairs = [(x, y) for x in free_a for y in free_b if x.name.startswith("Serial") == y.name.startswith("Serial")]
        if pairs:
            x, y = data.draw(st.sampled_from(pairs))
            x.connect(y)
            made += 1
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert [d.name for d in again.devices] == [d.name for d in devs]
    assert len(again.links) == made
    assert {(*l.ends, l.cable) for l in again.links} == {(*l.ends, l.cable) for l in net.links}
    assert again.duplicate_macs() == {}


def test_link_locals_follow_the_mac():
    """Packet Tracer shows the stored IPv6 link-local, EUI-64 of the port's MAC.
    Cloned devices used to keep their template's (found by the enterprise
    example: eight PCs on FE80::290:CFF:FEC7:8E5A)."""
    from pktlib._model import _link_local

    assert _link_local("0090.0CC7.8E5A") == "FE80::290:CFF:FEC7:8E5A"
    assert _link_local("0002.4A8B.0001") == "FE80::202:4AFF:FE8B:1"
    net = pktlib.new(seed=31)
    pcs = [net.pc(f"PC{i}") for i in range(10)]
    for pc in pcs:
        p = pc["fa0"]
        assert p.el.findtext("IPV6_LINK_LOCAL") == _link_local(p.mac)
    assert net.duplicate_link_locals() == {}


def test_link_locals_on_added_modules():
    from pktlib._model import _link_local

    r = pktlib.new(seed=32).router("R", "2911")
    r.add_module("HWIC-2T")
    for p in r.ports.values():
        ll = p.el.findtext("IPV6_LINK_LOCAL")
        if ll:
            assert ll == _link_local(p.mac)


def test_duplicate_link_locals_found():
    net = pktlib.new(seed=33)
    a, b = net.pc("A"), net.pc("B")
    req(b["fa0"].el, "IPV6_LINK_LOCAL").text = a["fa0"].el.findtext("IPV6_LINK_LOCAL")
    ((_ll, who),) = net.duplicate_link_locals().items()
    assert who == ["A.FastEthernet0", "B.FastEthernet0"]


def test_switch_flash_config_text_follows_the_config():
    """A switch saved with `write mem` has its startup config in flash as
    config.text, and Packet Tracer boots it from there, ignoring the running
    config in the file (found with a lecturer's starter file: the switches came
    back with the old banner and passwords). pktlib keeps it in step."""
    import xml.etree.ElementTree as ET

    sw = pktlib.new(seed=95).switch("S1")
    fm = sw.engine.find("FILE_MANAGER")
    if fm is None:
        fm = ET.SubElement(sw.engine, "FILE_MANAGER")
    f = ET.SubElement(fm, "FILE")
    ET.SubElement(f, "NAME").text = "config.text"
    cfg = ET.SubElement(ET.SubElement(f, "FILE_CONTENT"), "CONFIG")
    ET.SubElement(cfg, "LINE").text = "banner motd #old#"
    sw.config("banner motd #new#")
    flash = [l.text for l in cfg]
    assert "banner motd #new#" in flash and "banner motd #old#" not in flash
    assert flash == sw.running_config


def test_a_new_network_carries_nobody_s_paths():
    """Packet Tracer saves its recent-files list in every file. The base template came from
    a file saved on the author's PC, so every new network carried their Windows username and
    folder names until 27 Oct."""
    net = pktlib.new(seed=1)
    assert all(len(recent) == 0 for recent in net.root.iter("RECENT_FILES"))
    assert not re.search(r"[A-Za-z]:\\|\\Users\\|/Users/|/home/", net.to_xml().decode())


def test_no_file_in_the_repo_carries_a_recent_files_list():
    """Every sample saved in Packet Tracer carries the saver's recent files: on 27 Oct the
    first .pka samples brought a student ID and Windows folders back with them. Clear the
    list before committing a sample (scripts/make_templates.py shows how)."""
    root = Path(__file__).resolve().parents[1]
    files = [*root.glob("tests/fixtures/*.pk[at]"), *root.glob("scripts/sources/*.pk[at]")]
    files += root.glob("src/pktlib/data/*.xml.gz")
    assert len(files) > 10
    for f in files:
        raw = f.read_bytes()
        xml = gzip.decompress(raw) if f.suffix == ".gz" else decode(raw)
        assert not re.search(rb"<RECENT_FILES>\s*<(?!/)", xml), f.name


def test_reloading_with_the_build_seed_never_repeats_ids_or_macs(tmp_path):
    """Found by the state machine: a file loaded with the seed it was built with drew the
    same SAVE_REF_ID for the next new device as for the first, so a cable to the new one
    resolved to the old one."""
    net = pktlib.new(seed=0)
    first = net.router("R1", "2911")
    net.save(tmp_path / "a.pkt")
    again = pktlib.load(tmp_path / "a.pkt", seed=0)
    second = again.router("R2", "2911")
    assert second.ref != first.ref
    assert again.duplicate_macs() == {}
    second["g0/0"].connect(again["R1"]["g0/0"])
    assert again.links[0].ports == (second["g0/0"], again["R1"]["g0/0"])
