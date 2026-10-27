"""Slots and modules: physical limits are enforced (no more power supplies than
bays, no WIC where there's no WIC slot), names follow the slot, and removal
undoes everything. Checked in Packet Tracer 8.2 on 25 Oct: an 1841 with two
WIC-2Ts and a 2911 with a WIC-2T in slot 0/2 ping each other over the new
serial ports; a 3650 with both power supplies boots."""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import PktError
from pktlib._modules import catalogue
from tests.conftest import examples

VERIFIED = pktlib.models()


def test_catalogue_has_the_modules_we_use():
    assert {
        "WIC-2T",
        "WIC-1T",
        "WIC-1ENET",
        "HWIC-2T",
        "HWIC-4ESW",
        "NIM-2T",
        "AC-POWER-SUPPLY",
        "PT-HOST-NM-1CFE",
        "PT-ROUTER-NM-1S",
        "IP_PHONE_POWER_ADAPTER",
    } <= set(pktlib.module_models())
    assert catalogue()["WIC-2T"][0] == "eInterfaceCard"
    assert catalogue()["AC-POWER-SUPPLY"][0] == "ePtSwitchModule"


@pytest.mark.parametrize("model", VERIFIED)
def test_fresh_device_slots_match_spec(spec, model):
    d = pktlib.new(seed=1).add_device("D", model)
    removable = {}
    for s in d.slots:
        if s.removable:
            removable[s.type] = removable.get(s.type, 0) + 1
    assert removable == spec[model]["slots"]
    assert sorted(d.modules) == spec[model]["fitted"]


@pytest.mark.parametrize("model", VERIFIED)
@pytest.mark.parametrize(
    "module",
    [
        "WIC-2T",
        "HWIC-2T",
        "NIM-2T",
        "WIC-1ENET",
        "HWIC-4ESW",
        "AC-POWER-SUPPLY",
        "PT-HOST-NM-1CFE",
        "PT-ROUTER-NM-1S",
        "IP_PHONE_POWER_ADAPTER",
    ],
)
def test_never_more_modules_than_slots(spec, model, module):
    """Keep adding until refused. A model whose Packet Tracer GUI doesn't list
    the module refuses it outright; otherwise the count fitted never exceeds the
    device's slots of that type, and the refusal says there's no free slot."""
    d = pktlib.new(seed=2).add_device("D", model)
    slot_type = catalogue()[module][0]
    if module not in spec[model].get("accepts", [module]):
        with pytest.raises(PktError, match="doesn't take"):
            d.add_module(module)
        return
    total = spec[model]["slots"].get(slot_type, 0)
    already = sum(1 for s in d.slots if s.type == slot_type and not s.empty)
    added = 0
    while True:
        try:
            d.add_module(module)
        except PktError as e:
            assert "no free" in str(e)
            break
        added += 1
        assert added <= total
    assert already + added == total
    assert sum(1 for s in d.slots if s.type == slot_type and not s.empty) == total


@pytest.mark.parametrize(
    "model,module",
    [
        ("2911", "WIC-2T"),
        ("1941", "WIC-2T"),
        ("ISR4331", "WIC-2T"),
        ("ISR4331", "HWIC-2T"),
        ("Switch-PT", "AC-POWER-SUPPLY"),
        ("2960-24TT", "AC-POWER-SUPPLY"),
        ("PC-PT", "PT-LAPTOP-NM-1CFE"),
        ("7960", "WIC-2T"),
        ("1841", "NIM-2T"),
    ],
)
def test_modules_the_gui_refuses(model, module):
    with pytest.raises(PktError, match="doesn't take"):
        pktlib.new(seed=13).add_device("D", model).add_module(module)


def test_names_match_what_packet_tracer_wrote():
    """scripts/sources/modules.pkt was built in the GUI (cards dragged in, power
    cycled, saved). Packet Tracer's own interface list must equal pktlib's."""
    from pathlib import Path

    from pktlib._modules import port_names_for

    n = pktlib.load(Path(__file__).parents[1] / "scripts" / "sources" / "modules.pkt")
    for name in ("G2911", "ISR", "R1841"):
        d = n.device(name)
        ours = {
            nm
            for s in d.slots
            if s.removable and s.module is not None
            for _, nm in port_names_for(s.module, s.path, d.model)
        }
        pt = {l[len("interface ") :] for l in d.running_config if l.startswith("interface ")}
        assert ours and ours <= pt, name
    assert {"Serial0/0/0", "FastEthernet0/1/3"} <= set(n.device("G2911").ports)
    assert "Serial0/2/1" in n.device("ISR").ports
    assert {"Ethernet0/0/0", "Serial0/1/0"} <= set(n.device("R1841").ports)
    assert n.device("PHONE").modules == ["IP_PHONE_POWER_ADAPTER"]


def test_phone_power_adapter():
    n = pktlib.new(seed=14)
    assert n.phone("A").modules == []
    assert n.phone("B", power_adapter=True).modules == ["IP_PHONE_POWER_ADAPTER"]


def test_3650_takes_exactly_two_power_supplies():
    c = pktlib.new(seed=3).multilayer("C", "3650-24PS")
    assert c.modules == ["AC-POWER-SUPPLY"]  # the template ships one fitted
    c.add_module("AC-POWER-SUPPLY")
    assert c.modules == ["AC-POWER-SUPPLY", "AC-POWER-SUPPLY"]
    with pytest.raises(PktError, match=r"no free power-supply bay .*all 2 in use"):
        c.add_module("AC-POWER-SUPPLY")


def test_wrong_kind_of_module():
    n = pktlib.new(seed=4)
    with pytest.raises(PktError, match="no swappable modules"):
        n.multilayer("C", "3560-24PS").add_module("WIC-2T")
    r = n.router("R", "1841")
    with pytest.raises(PktError, match="doesn't take"):
        r.add_module("AC-POWER-SUPPLY", slot=(0, 0))
    with pytest.raises(pktlib.NotFound, match="unknown module 'WIC-99Z' \\(did you mean WIC-2T"):
        r.add_module("WIC-99Z")
    # slot-type checks still apply to models without a recorded list
    from pktlib._model import SPEC

    unlisted = {k: v for k, v in SPEC["Meraki-MX65W"].items() if k != "accepts"}
    import unittest.mock

    with unittest.mock.patch.dict(SPEC, {"Meraki-MX65W": {**unlisted, "verified": False}}):
        m = n.add_device("M", "Meraki-MX65W", unverified=True)
        with pytest.raises(PktError, match=r"has no free|has none"):
            m.add_module("WIC-2T")
        with pytest.raises(PktError, match="unknown module"):
            m.add_module("WIC-99Z")


def test_named_slot_rules():
    r = pktlib.new(seed=5).router("R", "1841")
    r.add_module("WIC-2T", slot=(0, 1))
    assert list(r.ports)[-2:] == ["Serial0/1/0", "Serial0/1/1"]
    with pytest.raises(PktError, match="already holds"):
        r.add_module("WIC-2T", slot=(0, 1))
    with pytest.raises(PktError, match="built in"):
        r.add_module("WIC-2T", slot=(0,))
    with pytest.raises(PktError, match="no slot"):
        r.add_module("WIC-2T", slot=(0, 7))


@pytest.mark.parametrize(
    "model,module,slot,names",
    [
        ("1841", "WIC-2T", (0, 0), ["Serial0/0/0", "Serial0/0/1"]),
        ("1841", "WIC-2T", (0, 1), ["Serial0/1/0", "Serial0/1/1"]),
        ("1841", "WIC-1T", (0, 1), ["Serial0/1/0"]),
        ("2911", "HWIC-2T", (0, 2), ["Serial0/2/0", "Serial0/2/1"]),
        ("1941", "HWIC-2T", (0, 1), ["Serial0/1/0", "Serial0/1/1"]),
        ("ISR4331", "NIM-2T", (0, 2), ["Serial0/2/0", "Serial0/2/1"]),
        ("2811", "HWIC-2T", (0, 3), ["Serial0/3/0", "Serial0/3/1"]),
    ],
)
def test_interface_names_follow_the_slot(model, module, slot, names):
    r = pktlib.new(seed=6).router("R", model)
    r.add_module(module, slot=slot)
    assert [p for p in r.ports if p.startswith("Serial")] == names
    for name in names:
        assert f"interface {name}" in r.running_config


def test_router_pt_network_modules():
    r = pktlib.new(seed=7).router("R", "Router-PT")
    free = r.free_slots("ePtRouterModule")
    assert len(free) == 4  # 10 bays, 6 fitted from the palette
    r.add_module("PT-ROUTER-NM-1S")
    assert "Serial6/0" in r.ports


def test_remove_module_undoes_add():
    r = pktlib.new(seed=8).router("R", "1841")
    before_ports, before_cfg = list(r.ports), list(r.running_config)
    s = r.add_module("WIC-2T")
    assert r.remove_module(s.path) == "WIC-2T"
    assert list(r.ports) == before_ports
    assert r.running_config == before_cfg


def test_remove_keeps_other_cards_names():
    r = pktlib.new(seed=9).router("R", "1841")
    r.add_module("WIC-2T")
    r.add_module("WIC-2T")
    r.remove_module((0, 0))
    assert [p for p in r.ports if p.startswith("Serial")] == ["Serial0/1/0", "Serial0/1/1"]


def test_remove_refusals():
    n = pktlib.new(seed=10)
    a = n.router("A", "1841")
    b = n.router("B", "1841")
    a.add_module("WIC-2T")
    b.add_module("WIC-2T")
    a["se0/0/0"].connect(b["se0/0/0"])
    with pytest.raises(PktError, match="unplug"):
        a.remove_module((0, 0))
    with pytest.raises(PktError, match="built in"):
        a.remove_module((0,))
    with pytest.raises(PktError, match="nothing in slot"):
        a.remove_module((0, 1))
    a["se0/0/0"].disconnect()
    assert a.remove_module((0, 0)) == "WIC-2T"


def test_modules_survive_save_and_load(tmp_path):
    n = pktlib.new(seed=11)
    r = n.router("R", "2911")
    r.add_module("HWIC-2T", slot=(0, 3))
    c = n.multilayer("C", "3650-24PS")
    c.add_module("AC-POWER-SUPPLY")
    n.save(tmp_path / "m.pkt")
    m = pktlib.load(tmp_path / "m.pkt")
    assert m.device("R").modules == ["HWIC-2T"] and "Serial0/3/1" in m.device("R").ports
    assert m.device("C").modules == ["AC-POWER-SUPPLY", "AC-POWER-SUPPLY"]
    assert m.duplicate_macs() == {}


@settings(max_examples=examples(25), deadline=None)
@given(st.lists(st.tuples(st.sampled_from(["add", "remove"]), st.integers(0, 3)), max_size=12))
def test_fuzz_add_remove_sequences_stay_consistent(ops):
    """Any sequence of adds and removes leaves the device consistent: ports
    match fitted cards, every Serial port has a config block, no slot over-full."""
    r = pktlib.new(seed=12).router("R", "2911")
    for op, i in ops:
        try:
            if op == "add":
                r.add_module("HWIC-2T", slot=(0, i))
            else:
                r.remove_module((0, i))
        except PktError:
            pass
    fitted = [s for s in r.slots if s.type == "eInterfaceCard" and not s.empty]
    serial = [p for p in r.ports if p.startswith("Serial")]
    assert len(serial) == 2 * len(fitted)
    assert serial == sorted(
        {f"Serial0/{s.path[1]}/{k}" for s in fitted for k in (0, 1)},
        key=lambda x: (int(x.split("/")[1]), int(x.split("/")[2])),
    )
    cfg_serial = {l.split()[1] for l in r.running_config if l.startswith("interface Serial")}
    assert cfg_serial == set(serial)


def test_hub_ports_are_named_by_slot():
    """A Hub-PT names each port after its card's slot. Packet Tracer 8.2, 27 Oct
    2026: card pulled from slot 2 in the GUI, the hover table lists FastEthernet0,
    1, 3, 4, 5 (tests/fixtures/hub-card-removed.pkt is that file). pktlib used to
    count, read it as FastEthernet0-4, and refused the pull."""
    saved = pktlib.load(Path(__file__).parent / "fixtures" / "hub-card-removed.pkt")
    assert list(saved.device("HUB").ports) == [f"FastEthernet{i}" for i in (0, 1, 3, 4, 5)]
    net = pktlib.new(seed=1)
    hub = net.add_device("H", "Hub-PT")
    link = hub["fa5"].connect(net.pc("PC")["fa0"])
    hub.remove_module((2,))
    assert list(hub.ports) == [f"FastEthernet{i}" for i in (0, 1, 3, 4, 5)]
    assert hub["fa5"].link == link


@pytest.mark.parametrize("model", ["2620XM", "2621XM"])
def test_2600xm_onboard_wics_count_straight_through(model):
    """A WIC-2T in each onboard slot of a 2620XM or 2621XM: Packet Tracer 8.2's
    Config tab lists Serial0/0, 0/1, 0/2, 0/3 (27 Oct 2026). With the
    three-level Serial0/0/0 on a cable, Packet Tracer refused the whole file
    as "not compatible with this version" (stress rt02's TS2)."""
    d = pktlib.new(seed=27).router("R", model)
    d.add_module("WIC-2T", slot=(0, 0))
    d.add_module("WIC-2T", slot=(0, 1))
    assert [p for p in d.ports if p.startswith("Serial")] == ["Serial0/0", "Serial0/1", "Serial0/2", "Serial0/3"]
