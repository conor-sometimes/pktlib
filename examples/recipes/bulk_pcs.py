"""Add 30 PCs from a table (name, address, VLAN), each on the next free switch port, in a tidy grid.

    uv run python examples/recipes/bulk_pcs.py               # the table below, into classroom.pkt
    uv run python examples/recipes/bulk_pcs.py pcs.csv       # your own table: name,address,vlan per line

Shows: reading a table with `csv`, finding free ports with `port.link is None`,
adding a second switch (trunked to the first) when the first is full, setting
the access VLAN per port, a router sub-interface per VLAN, and placing
devices with `at=` on a grid.
"""

import csv
import io
import ipaddress
import sys
from pathlib import Path

import pktlib

# name, address/prefix, VLAN. In real life: an export from the timetable or the asset list.
TABLE = "\n".join(
    f"{room}-PC{n:02},10.{vlan}.0.{10 + n}/24,{vlan}"
    for room, vlan, count in (("LAB1", 10, 12), ("LAB2", 20, 12), ("STAFF", 30, 6))
    for n in range(1, count + 1)
)
COLUMNS = 8  # PCs per row, under their switch

text = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else TABLE
rows = [row for row in csv.reader(io.StringIO(text)) if row]

net = pktlib.new(seed=5)
r1 = net.router("R1", "2911", at=(500, 40))
switches: list[pktlib.Device] = []


def new_switch() -> pktlib.Device:
    """SW1 hangs off R1; each later one off the switch before it, on a trunk."""
    sw = net.switch(f"SW{len(switches) + 1}", at=(500 + 1000 * len(switches), 180))
    uplink = r1["g0/0"] if not switches else switches[-1]["g0/2"]
    sw["g0/1"].connect(uplink)
    for d, p in ((sw, "g0/1"), (uplink.device, uplink.name)):
        if d is not r1:
            d.config(f"interface {p}\n switchport mode trunk")
    switches.append(sw)
    return sw


def free_port() -> pktlib.Port:
    """The next uncabled FastEthernet port, on a new switch if every one is full."""
    for sw in switches:
        for port in sw:
            if port.name.startswith("FastEthernet") and port.link is None:
                return port
    return next(p for p in new_switch() if p.name.startswith("FastEthernet"))


gateways = {}  # VLAN -> (gateway, network)
for name, address, vlan in rows:
    iface = ipaddress.IPv4Interface(address)
    gw = next(iface.network.hosts())  # the first address in each subnet is its gateway
    gateways[int(vlan)] = (gw, iface.network)
    port = free_port()
    sx, sy = port.device.xy
    n = sum(1 for p in port.device if p.link is not None) - 1  # PCs already on this switch
    pc = net.pc(name, at=(sx - 420 + 120 * (n % COLUMNS), sy + 150 + 110 * (n // COLUMNS)), ip=address, gateway=str(gw))
    port.connect(pc["fa0"])
    port.device.config(f"interface {port.name}\n switchport mode access\n switchport access vlan {vlan}")

r1.config("interface g0/0\n no shutdown")
for vlan, (gw, network) in sorted(gateways.items()):
    r1.config(f"interface g0/0.{vlan}\n encapsulation dot1Q {vlan}\n ip address {gw} {network.netmask}")

net.around(*switches, *[d for d in net if d.kind == "Pc"], shape="rectangle", outline="blue", label="CLASSROOMS")
net.ping(rows[0][0], rows[-1][0], scenario="First PC to last PC")
net.save("classroom.pkt")
print(f"classroom.pkt: {len(rows)} PCs on {len(switches)} switches, VLANs {sorted(gateways)}")
