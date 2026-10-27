"""List every device, port, address and cable in a .pkt file.

    uv run python examples/recipes/inventory.py              # builds sample.pkt and lists it
    uv run python examples/recipes/inventory.py lab.pkt      # lists your file

Shows: loading a file, walking `for device in net` and `for port in device`,
reading `port.address`, `port.access_vlan`, `port.peer`, and `net.links`.
"""

import sys

import pktlib


def sample() -> pktlib.Network:
    """A small office to list: a router, a switch with two VLANs, three hosts."""
    net = pktlib.new(seed=1)
    r1 = net.router("R1", "2911", at=(300, 100))
    sw = net.switch("SW1", at=(300, 220))
    r1["g0/0"].connect(sw["g0/1"])
    r1.config(
        "interface g0/0\n no shutdown\n"
        + "".join(
            f"interface g0/0.{v}\n encapsulation dot1Q {v}\n ip address 192.168.{v}.1 255.255.255.0\n" for v in (10, 20)
        )
    )
    sw.config("interface g0/1\n switchport mode trunk")
    for i, (name, vid) in enumerate((("PC1", 10), ("PC2", 10), ("PRINTER", 20)), 1):
        make = net.printer if name == "PRINTER" else net.pc
        host = make(name, at=(150 * i, 340), ip=f"192.168.{vid}.{10 + i}/24", gateway=f"192.168.{vid}.1")
        sw[f"fa0/{i}"].connect(host["fa0"])
        sw.config(f"interface fa0/{i}\n switchport mode access\n switchport access vlan {vid}")
    net.ping("PC1", "PRINTER", scenario="PC1 to the printer")
    net.save("sample.pkt")
    return net


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()

print(f"{len(net)} devices, {len(net.links)} cables\n")
for device in net:
    print(f"{device.name}  ({device.model}, {device.kind})")
    for port in device:
        if port.link is None and port.address is None:
            continue  # skip spare ports: nothing cabled, no address
        what = []
        if port.address:
            what.append(port.address)
        if port.access_vlan:
            what.append(f"VLAN {port.access_vlan}")
        if port.mode == "trunk":
            what.append("trunk")
        if port.peer is not None:
            what.append(f"to {port.peer.device.name} {port.peer.name}")
        print(f"    {port.name:24} {'  '.join(what)}")
    # sub-interfaces and SVIs live in the config, not on a port
    for name, iface in device.interfaces.items():
        if ("." in name or name.startswith("Vlan")) and iface.address:
            print(f"    {name:24} {iface.address}")
    if not device.has_ios:  # end devices: a gateway, or DHCP
        print(f"    {'DHCP' if device.dhcp else 'gateway ' + (device.gateway or '(none)')}")

print("\nCables:")
for link in net.links:
    (a, ap), (b, bp) = link.ends
    print(f"    {a} {ap}  <-{link.cable}->  {b} {bp}")
