"""Find everything in one VLAN: access and voice ports, the devices on them, trunks that carry it, its gateways.

    uv run python examples/recipes/find_vlan.py              # VLAN 10 in sample.pkt
    uv run python examples/recipes/find_vlan.py lab.pkt 20

Shows: `port.access_vlan`, `port.voice_vlan`, `port.mode`, `port.peer` (who is
plugged in), `port.setting("switchport trunk allowed vlan")` for pruned
trunks, `device.vlans` (the VLAN database), and `device.interface_config` to
find the router sub-interface or SVI that routes the VLAN.
"""

import sys

import pktlib


def sample() -> pktlib.Network:
    """Two switches on a trunk that carries only VLANs 10 and 20, a router on a stick, a phone."""
    net = pktlib.new(seed=10)
    r1 = net.router("R1", "2911", at=(400, 60))
    sw1 = net.multilayer("SW1", "3560-24PS", at=(250, 200))  # PoE, for the phone
    sw2 = net.switch("SW2", at=(550, 200))
    r1["g0/0"].connect(sw1["g0/1"])
    sw1["g0/2"].connect(sw2["g0/1"])
    sw1.config(
        "cdp run\n"
        "interface g0/1\n switchport trunk encapsulation dot1q\n switchport mode trunk\n"
        "interface g0/2\n switchport trunk encapsulation dot1q\n switchport mode trunk\n"
        " switchport trunk allowed vlan 10,20"
    )
    sw2.config("interface g0/1\n switchport mode trunk\n switchport trunk allowed vlan 10,20")
    r1.config("interface g0/0\n no shutdown")
    for vid, name in ((10, "STAFF"), (20, "LAB"), (30, "VOICE")):
        r1.config(f"interface g0/0.{vid}\n encapsulation dot1Q {vid}\n ip address 10.0.{vid}.1 255.255.255.0")
        for sw in (sw1, sw2):
            sw.add_vlan(vid, name)
    hosts = [(sw1, "PC1", 10), (sw1, "PC2", 20), (sw2, "PC3", 10), (sw2, "PC4", 20)]
    for i, (sw, name, vid) in enumerate(hosts):
        pc = net.pc(name, at=(100 + 150 * i, 340), ip=f"10.0.{vid}.{11 + i}/24", gateway=f"10.0.{vid}.1")
        port = f"fa0/{1 + i % 2}"
        sw[port].connect(pc["fa0"])
        sw.config(f"interface {port}\n switchport mode access\n switchport access vlan {vid}")
    phone = net.phone("PHONE1", at=(100, 460))
    sw1["fa0/10"].connect(phone["Switch"])
    sw1.config("interface fa0/10\n switchport mode access\n switchport access vlan 10\n switchport voice vlan 30")
    net.ping("PC1", "PC3", scenario="VLAN 10 across the trunk")
    net.save("sample.pkt")
    return net


def vlan_list(text: str) -> set[int]:
    """'10,20-22' -> {10, 20, 21, 22}."""
    out: set[int] = set()
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


args = sys.argv[1:]
net = pktlib.load(args.pop(0)) if args and args[0].endswith(".pkt") else sample()
vlan = int(args[0]) if args else 10

print(f"VLAN {vlan}:")
for device in net:
    if vlan in device.vlans and device.kind in ("Switch", "MultiLayerSwitch"):
        print(f"  {device.name}: in the VLAN database as {device.vlans[vlan]!r}")
    for port in device:
        who = f"{port.peer.device.name} ({port.peer.device.kind})" if port.peer else "nothing plugged in"
        if port.access_vlan == vlan and port.mode != "trunk":
            print(f"    {device.name} {port.name}: access port, {who}")
        if port.voice_vlan == vlan:
            print(f"    {device.name} {port.name}: voice VLAN, {who}")
        if port.mode == "trunk":
            allowed = port.setting("switchport trunk allowed vlan")
            if allowed is None or vlan in vlan_list(allowed.split()[-1]):
                print(f"    {device.name} {port.name}: trunk carrying it, to {who}")
    if device.has_ios:  # a sub-interface tagged with the VLAN, or its SVI
        for name, iface in device.interfaces.items():
            tag = device.interface_config(name).get("encapsulation dot1Q", "")
            if tag.split()[2:3] == [str(vlan)] or name == f"Vlan{vlan}":
                print(f"    {device.name} {name}: routes it, {iface.address or 'no address'}")
