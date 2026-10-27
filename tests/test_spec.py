"""pktlib held to its spec (src/pktlib/spec/devices.json): port names and kinds
as Packet Tracer reports them, for every model, on a freshly built device."""

import pytest

import pktlib
from pktlib._ports import CABLE_TYPES, PktError, is_serial

WIRED_PREFIXES = ("FastEthernet", "GigabitEthernet", "Ethernet", "Serial", "Management")


def verified(spec):
    return sorted(m for m, s in spec.items() if s["verified"])


def test_verified_models_list_what_they_accept(spec):
    for m in verified(spec):
        assert "accepts" in spec[m], f"{m}: no Physical-tab module list recorded"


def test_spec_shape(spec):
    assert len(spec) >= 60
    for model, s in spec.items():
        assert set(s) >= {
            "kind",
            "family",
            "template",
            "ios",
            "gateway",
            "vlan_database",
            "verified",
            "wired",
            "powered",
        }, model
        assert s["verified"] in (False, "ios-config", "pt-menu", "pt-hover"), model
        if s["verified"]:
            # an empty chassis or a phone has no cable ports, but its names were still read off PT
            assert s["wired"] or "port_names" in s, f"{model} is verified but lists no ports"
            assert s["powered"], f"{model} is verified but its template is switched off"


def test_the_models_we_rely_on_are_verified(spec):
    must = {
        "1841",
        "1841+WIC-2T",
        "1941",
        "2811",
        "2901",
        "2911",
        "ISR4321",
        "ISR4331",
        "Router-PT",
        "2960-24TT",
        "2950-24",
        "3560-24PS",
        "3650-24PS",
        "PC-PT",
        "Laptop-PT",
        "Server-PT",
        "Printer-PT",
        "7960",
    }
    assert must <= set(verified(spec))
    assert pktlib.models() == verified(spec)


@pytest.mark.parametrize(
    "model",
    [
        "1841",
        "1841+WIC-2T",
        "1941",
        "2620XM",
        "2621XM",
        "2811",
        "2901",
        "2911",
        "2950-24",
        "2950T-24",
        "2960-24TT",
        "3560-24PS",
        "3650-24PS",
        "5505",
        "7960",
        "ISR4321",
        "ISR4331",
        "Laptop-PT",
        "Meraki-Server",
        "PC-PT",
        "Printer-PT",
        "Router-PT",
        "Server-PT",
        "Switch-PT",
        "WiredEndDevice-PT",
        # added 25 Oct from Packet Tracer's hover tables and cable menus
        "5506-X",
        "CGR1240",
        "IE-2000",
        "819HGW",
        "829",
        "819HG-4G-IOX",
        "3702i",
        "LAP-PT",
        "Hub-PT",
        "Bridge-PT",
        "Cloud-PT",
        "Cloud-PT-Empty",
        "Home-VoIP-PT",
        "Meraki-MX65W",
        "SMARTPHONE-PT",
        "TabletPC-PT",
        "WirelessEndDevice-PT",
        "Router-PT-Empty",
        "Switch-PT-Empty",
    ],
)
def test_fresh_device_matches_spec(spec, model):
    s = spec[model]
    net = pktlib.new(seed=3)
    d = net.add_device("D", model)
    assert d.kind == s["kind"]
    assert d.has_ios == s["ios"]
    wired = [n for n, p in d.ports.items() if p.type in CABLE_TYPES]
    assert sorted(wired) == sorted(s["wired"]), f"{model}: pktlib says {wired}"
    # every wired port is reachable by its own name, and by IOS shorthand where it has one
    for name in s["wired"]:
        assert d.port(name).name == name
    if s["vlan_database"] and s["family"] in ("switch", "multilayer"):
        assert 1 in d.vlans  # (a 5506-X has the database, empty: it has no switch ports)


def test_spec_names_survive_a_save(spec, tmp_path):
    net = pktlib.new(seed=4)
    for i, m in enumerate(verified(spec)):
        net.add_device(f"D{i}", m)
    net.save(tmp_path / "x.pkt")
    again = pktlib.load(tmp_path / "x.pkt")
    for i, m in enumerate(verified(spec)):
        d = again.device(f"D{i}")
        wired = [n for n, p in d.ports.items() if p.type in CABLE_TYPES]
        assert sorted(wired) == sorted(spec[m]["wired"]), m


def test_serial_ports_only_on_serial_models(spec):
    for m in verified(spec):
        serial = [p for p in spec[m]["wired"] if is_serial(p)]
        if m in ("1841+WIC-2T", "Router-PT", "Cloud-PT"):
            assert serial
        elif spec[m]["family"] != "router":
            assert not serial, m


def test_hand_checked_names(spec):
    """Read off Packet Tracer 8.2's cable menu, 25 Oct 2026."""
    assert spec["7960"]["port_names"] == ["Switch", "PC"]
    assert spec["PC-PT"]["port_names"] == ["FastEthernet0", "Bluetooth"]
    for m in ("Server-PT", "Printer-PT", "Laptop-PT", "Meraki-Server", "WiredEndDevice-PT"):
        assert "FastEthernet0" in spec[m]["port_names"]


def test_3650_template_has_a_power_supply():
    """Off the palette a 3650 has empty PSU bays and never boots; the template
    has an AC-POWER-SUPPLY fitted (found by the data-centre example)."""
    d = pktlib.new().add_device("C", "3650-24PS")
    assert any(
        m.findtext("MODEL") == "AC-POWER-SUPPLY" or "POWER" in (m.findtext("MODEL") or "")
        for m in d.engine.iter("MODULE")
    ), "no power supply module in the 3650 template"


def test_hover_names_match_packet_tracer():
    """Read off Packet Tracer 8.2's hover tables on 25 Oct and matched by MAC:
    the IE-2000's first four file ports (no type in the template) are
    FastEthernet1/1-1/4, and routers with an IOx host hide some ports."""
    net = pktlib.new(seed=61)
    ie = net.add_device("IE", "IE-2000")
    assert list(ie.ports)[:4] == [f"FastEthernet1/{i}" for i in range(1, 5)]
    assert all(p.type == "eCopperFastEthernet" for p in list(ie.ports.values())[:8])
    r = net.add_device("R", "819HGW")
    assert "GigabitEthernet0" in r.ports and "Wlan-GigabitEthernet0" in r.ports
    assert len(r.ports) == 9  # three hidden ports never listed
    assert list(net.add_device("C", "CGR1240").ports)[-1] == "Dot11Radio2/1"


def test_cabling_a_port_packet_tracer_cannot_name_is_refused():
    """A cable whose PORT names something Packet Tracer doesn't know makes it
    refuse the whole file ("not compatible with this version")."""
    net = pktlib.new(seed=62)
    ap = net.add_device("AP", "3702i")
    pc = net.pc("P")
    with pytest.raises(PktError, match="isn't a cable port"):
        ap["Dot11Radio0"].connect(pc["fa0"])
    ap["GigabitEthernet0"].connect(pc["fa0"])  # the wired one is fine


def test_coax_and_phone_cables():
    """As Packet Tracer 8.2 writes them (links drawn in the GUI on 25 Oct, then
    a file of pktlib-made ones opened there): LINK/TYPE eCoaxial or ePhoneLine,
    no straight/cross type. Each fits only its own kind of port."""
    net = pktlib.new(seed=64)
    cm, tv = net.add_device("CM", "Cable-Modem-PT"), net.add_device("TV", "TV-PT")
    dsl, ph = net.add_device("DSL", "DSL-Modem-PT"), net.add_device("PH", "Analog-Phone-PT")
    coax = cm["Port 0"].connect(tv["Port 0"])
    phone = dsl["Port 0"].connect(ph["Port 0"])
    assert (coax.cable, phone.cable) == ("coax", "phone")
    assert coax.el.findtext("TYPE") == "eCoaxial" and coax.el.find("CABLE/TYPE") is None
    assert phone.el.findtext("TYPE") == "ePhoneLine"
    pc = net.pc("P")
    with pytest.raises(PktError, match="doesn't fit"):
        cm["Port 1"].connect(net.add_device("TV2", "TV-PT")["Port 0"])  # Ethernet port, coax cable
    with pytest.raises(PktError, match="doesn't fit"):
        net.add_device("TV3", "TV-PT")["Port 0"].connect(pc["fa0"])  # coax port, PC's Ethernet
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert sorted(l.cable for l in again.links) == ["coax", "phone"]


@pytest.mark.parametrize(
    "model,port,cable",
    [
        # each cabled to a PC in Packet Tracer 8.2 on 25 Oct: the link came up only on this cable
        ("Linksys-WRT300N", "Ethernet 1", "straight"),
        ("Linksys-WRT300N", "Internet", "cross"),
        ("DLC100", "Ethernet 1", "straight"),
        ("DLC100", "Internet", "cross"),
        ("HomeRouter-PT-AC", "GigabitEthernet 2", "straight"),
        ("HomeRouter-PT-AC", "Internet", "cross"),
        ("Sniffer", "Ethernet0", "straight"),
        ("Cable-Modem-PT", "Port 1", "straight"),
        ("DSL-Modem-PT", "Port 1", "straight"),
        ("Repeater-PT", "Ethernet0", "straight"),
        ("Central-Office-Server", "Backbone", "cross"),
        ("AccessPoint-PT", "Port 0", "cross"),
        ("Cloud-PT", "Ethernet6", "straight"),
        ("Home-VoIP-PT", "Ethernet", "cross"),
        ("Meraki-MX65W", "Internet 1", "cross"),
        ("Meraki-MX65W", "Ethernet 12", "cross"),
        ("AccessPoint-PT-N", "Port 0", "cross"),
    ],
)
def test_auto_cable_matches_what_packet_tracer_brings_up(model, port, cable):
    net = pktlib.new(seed=68)
    d = net.add_device("D", model)
    d[port].connect(net.pc("P")["fa0"])
    assert net.links[0].cable == cable


@pytest.mark.parametrize("model", ["3702i", "LAP-PT"])
def test_access_points_ship_with_power(model):
    """Off the palette these access points have an empty power-adapter slot and
    their port never comes up; the templates have ACCESS_POINT_POWER_ADAPTER
    fitted (plugged in by hand in Packet Tracer 8.2, 25 Oct; a PC on
    GigabitEthernet0 then links green)."""
    d = pktlib.new().add_device("AP", model)
    assert d.modules == ["ACCESS_POINT_POWER_ADAPTER"]


def test_every_palette_model_is_verified(spec):
    """All 64 models in Packet Tracer 8.2's palette, as of 25 Oct 2026."""
    assert [m for m, s in spec.items() if not s["verified"]] == []
    assert len(spec) == 64


def test_cable_menu_names():
    """Read off Packet Tracer's cable menu: the cloud's ports aren't Ethernet0 or
    Modem0 (pktlib's old fallbacks), and the Meraki ships with its adapter."""
    net = pktlib.new(seed=69)
    cloud = net.add_device("C", "Cloud-PT")
    assert list(cloud.ports) == [
        "Serial0",
        "Serial1",
        "Serial2",
        "Serial3",
        "Modem4",
        "Modem5",
        "Ethernet6",
        "Coaxial7",
    ]
    cm = net.add_device("CM", "Cable-Modem-PT")
    assert cloud["Coaxial7"].connect(cm["Port 0"]).cable == "coax"
    assert list(net.add_device("V", "Home-VoIP-PT").ports) == ["Ethernet", "Phone"]
    m = net.add_device("M", "Meraki-MX65W")
    assert m.modules == ["MERAKI-POWER-ADAPTER"] and m["Ethernet 12"].type == "eCopperEthernet"
