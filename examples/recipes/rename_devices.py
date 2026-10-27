"""Rename every device to a naming scheme (SITE-ROLE-NN), hostnames included.

    uv run python examples/recipes/rename_devices.py         # renames sample.pkt into renamed.pkt
    uv run python examples/recipes/rename_devices.py lab.pkt DUB

Shows: `device.name = ...` (the label on the workspace), and setting the IOS
hostname with `config("hostname ...")`, since the two are separate in Packet
Tracer: renaming the label leaves `show run` saying Router0. Ping checks
and cables follow the device, so nothing else needs fixing up.
"""

import sys
from collections import Counter

import pktlib

ROLES = {  # device.kind -> the role in the name
    "Router": "RTR",
    "Switch": "SW",
    "MultiLayerSwitch": "MLS",
    "Pc": "PC",
    "Laptop": "LT",
    "Server": "SRV",
    "Printer": "PRN",
}


def sample() -> pktlib.Network:
    """A file with Packet Tracer's default names, as a student leaves it."""
    net = pktlib.new(seed=6)
    r = net.router("Router0", "1941", at=(300, 100))
    sw = net.switch("Switch0", at=(300, 220))
    sw["g0/1"].connect(r["g0/0"])
    r["g0/0"].address = "10.0.0.1/24"
    hosts = [
        net.pc("PC0", at=(100, 340), ip="10.0.0.10/24", gateway="10.0.0.1"),
        net.pc("PC1", at=(250, 340), ip="10.0.0.11/24", gateway="10.0.0.1"),
        net.laptop("Laptop0", at=(400, 340), ip="10.0.0.12/24", gateway="10.0.0.1"),
        net.server("Server0", at=(550, 340), ip="10.0.0.100/24", gateway="10.0.0.1"),
    ]
    for i, h in enumerate(hosts, 1):
        sw[f"fa0/{i}"].connect(h["fa0"])
    net.ping("PC0", "Server0", scenario="PC to server")
    net.save("sample.pkt")
    return net


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()
site = sys.argv[2] if len(sys.argv) > 2 else "HQ"

# number devices left to right, top to bottom, so PC-01 is the one on the left
count: Counter[str] = Counter()
for device in sorted(net, key=lambda d: (round(d.xy[1], -1), d.xy[0])):
    role = ROLES.get(device.kind, device.kind.upper())
    count[role] += 1
    old, new = device.name, f"{site}-{role}-{count[role]:02}"
    device.name = new
    if device.has_ios and device.kind in ("Router", "Switch", "MultiLayerSwitch"):
        device.config(f"hostname {new}")
    print(f"{old:10} -> {new}")

net.save("renamed.pkt")
print("wrote renamed.pkt; ping checks now:", ", ".join(f"{p.source} to {p.destination}" for p in net.pdus))
