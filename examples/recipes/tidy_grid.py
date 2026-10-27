"""Move a messy network's devices into a tidy layout: routers on top, switches below, each host under its switch.

    uv run python examples/recipes/tidy_grid.py              # tidies sample.pkt into tidy.pkt
    uv run python examples/recipes/tidy_grid.py lab.pkt

Shows: setting `device.xy`, sorting devices by `device.kind`, and following
cables with `device.neighbors` to keep each host under the switch it plugs
into. Cables, config and ping checks don't care where a device sits; drawn
shapes and notes stay where they were.
"""

import random
import sys

import pktlib

TIERS = {"Router": 0, "MultiLayerSwitch": 1, "Switch": 2}  # anything else is a host, tier 3
X0, Y0, DX, DY = 100, 80, 150, 140


def sample() -> pktlib.Network:
    """A small network dropped anywhere, as files end up after a few lessons."""
    rng = random.Random(9)
    net = pktlib.new(seed=9)

    def anywhere() -> tuple[int, int]:
        return rng.randrange(0, 1200), rng.randrange(0, 700)

    r1 = net.router("R1", "2911", at=anywhere())
    for s in (1, 2):
        sw = net.switch(f"SW{s}", at=anywhere())
        sw["g0/1"].connect(r1[f"g0/{s - 1}"])
        r1[f"g0/{s - 1}"].address = f"10.{s}.0.1/24"
        for h in (1, 2, 3):
            pc = net.pc(f"PC{s}{h}", at=anywhere(), ip=f"10.{s}.0.{10 + h}/24", gateway=f"10.{s}.0.1")
            sw[f"fa0/{h}"].connect(pc["fa0"])
    net.ping("PC11", "PC23", scenario="Across R1")
    net.save("sample.pkt")
    return net


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()

tiers: dict[int, list[pktlib.Device]] = {0: [], 1: [], 2: [], 3: []}
for d in sorted(net, key=lambda d: d.name):
    tiers[TIERS.get(d.kind, 3)].append(d)

# hosts go under the switch they're cabled to, in that switch's order; the rest after them
hosts: list[pktlib.Device] = []
for sw in tiers[1] + tiers[2]:
    hosts += [n for n in sw.neighbors if TIERS.get(n.kind, 3) == 3 and n not in hosts]
hosts += [d for d in tiers[3] if d not in hosts]
tiers[3] = hosts

# switches spread out to sit over their hosts; every other tier is centred
rows = [devices for devices in tiers.values() if devices]  # no gap for a tier this file hasn't got
width = max(len(row) for row in rows)
for level, devices in enumerate(rows):
    offset = (width - len(devices)) * DX / 2
    for i, d in enumerate(devices):
        d.xy = (X0 + offset + i * DX, Y0 + level * DY)
for sw in tiers[1] + tiers[2]:  # centre each switch over its own hosts
    mine = [h.xy[0] for h in sw.neighbors if h in hosts]
    if mine:
        sw.xy = (sum(mine) / len(mine), sw.xy[1])

net.save("tidy.pkt")
for level, devices in enumerate(rows):
    print(f"row {level}: {', '.join(d.name for d in devices)}")
