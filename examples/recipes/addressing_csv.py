"""Export a network's addressing table (device, interface, address, mask, gateway, VLAN) to CSV.

    uv run python examples/recipes/addressing_csv.py         # builds sample.pkt, writes addressing.csv
    uv run python examples/recipes/addressing_csv.py lab.pkt

Shows: `device.interfaces` for routers and switches (sub-interfaces, SVIs and
loopbacks included), `port.address` and `device.gateway` for end devices, and
which switch port and VLAN each host is plugged into, via `port.peer`. Open the
CSV in a spreadsheet, or paste it into a lab brief.
"""

import csv
import ipaddress
import sys

import pktlib


def sample() -> pktlib.Network:
    """A router with a loopback and two sub-interfaces, a switch with a management SVI, four hosts."""
    net = pktlib.new(seed=2)
    r1 = net.router("R1", "2911", at=(300, 100))
    sw = net.switch("SW1", at=(300, 220))
    r1["g0/0"].connect(sw["g0/1"])
    r1.config("""
interface loopback 0
 ip address 10.255.0.1 255.255.255.255
interface g0/0
 no shutdown
interface g0/0.10
 encapsulation dot1Q 10
 ip address 10.1.10.1 255.255.255.0
interface g0/0.99
 encapsulation dot1Q 99
 ip address 10.1.99.1 255.255.255.0
""")
    sw.config("""
interface g0/1
 switchport mode trunk
interface vlan 99
 ip address 10.1.99.2 255.255.255.0
ip default-gateway 10.1.99.1
""")
    sw.add_vlan(99, "MGMT")
    for i in range(1, 5):
        pc = net.pc(f"PC{i}", at=(80 + 150 * i, 340), ip=f"10.1.10.{10 + i}/24", gateway="10.1.10.1")
        sw[f"fa0/{i}"].connect(pc["fa0"])
        sw.config(f"interface fa0/{i}\n switchport mode access\n switchport access vlan 10")
    net.ping("PC1", "R1", ip="10.255.0.1", scenario="PC1 to the router loopback")
    net.save("sample.pkt")
    return net


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()

rows = []
for device in net:
    if device.has_ios:
        # routers and switches: every interface IOS has an address on
        for name, iface in device.interfaces.items():
            if iface.address:
                addr = ipaddress.IPv4Interface(iface.address)
                rows.append([device.name, name, str(addr.ip), str(addr.netmask), "", ""])
    else:
        # end devices: each addressed port, its gateway, and the VLAN of the switch port it plugs into
        for port in device:
            if port.address:
                vlan = port.peer.access_vlan if port.peer is not None else None
                rows.append([device.name, port.name, port.ip, port.mask, device.gateway, vlan or ""])

with open("addressing.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["device", "interface", "address", "mask", "gateway", "vlan"])
    writer.writerows(rows)
print(f"wrote addressing.csv: {len(rows)} addresses")
for row in rows:
    print("  " + ", ".join(str(c) for c in row))
