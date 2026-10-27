"""Replace every router of one model with another (1841 to 1941 here), keeping cables, config and ping checks.

    uv run python examples/recipes/swap_model.py             # swaps the 1841s in sample.pkt, writes swapped.pkt
    uv run python examples/recipes/swap_model.py lab.pkt

pktlib can't change a device's model in place, so this does what you would do
by hand: note the old router's cables, config and ping checks, delete it, add
the new model with the same name and position, fit the serial card, and put it
all back with the interface names mapped (FastEthernet0/0 becomes
GigabitEthernet0/0). Only config that differs from a factory-fresh router is
carried over, so the new router keeps its own defaults.

Shows: `device.links`, `link.other(port)`, `net.pdus`, `net.remove_device`,
`add_module`, and `config()` with a list of lines.
"""

import itertools
import sys

import pktlib

OLD, NEW = "1841", "1941"
CARDS = [("HWIC-2T", (0, 0))]  # the 1941's serial card, where the 1841's WIC-2T was
PORTS = {  # old interface name -> new
    "FastEthernet0/0": "GigabitEthernet0/0",
    "FastEthernet0/1": "GigabitEthernet0/1",
    "Serial0/0/0": "Serial0/0/0",
    "Serial0/0/1": "Serial0/0/1",
}


def sample() -> pktlib.Network:
    """Three 1841s in a serial chain running OSPF, a PC at each end."""
    net = pktlib.new(seed=12)
    routers = [net.router(f"R{i}", "1841+WIC-2T", at=(150 + 250 * i, 150)) for i in range(3)]
    for i, (a, b) in enumerate(itertools.pairwise(routers)):
        a["se0/0/0"].connect(b["se0/0/1"])
        a["se0/0/0"].address = f"10.0.{i}.1/30"
        b["se0/0/1"].address = f"10.0.{i}.2/30"
    for n, r in ((1, routers[0]), (2, routers[-1])):
        pc = net.pc(f"PC{n}", at=(r.xy[0], 300), ip=f"192.168.{n}.10/24", gateway=f"192.168.{n}.1")
        r["fa0/0"].connect(pc["fa0"])
        r["fa0/0"].address = f"192.168.{n}.1/24"
    for r in routers:
        r.config("router ospf 1\n network 10.0.0.0 0.0.255.255 area 0\n network 192.168.0.0 0.0.255.255 area 0")
    net.ping("PC1", "PC2", scenario="End to end")
    net.ping("PC1", "R1", ip="10.0.0.2", scenario="End to end")
    net.save("sample.pkt")
    return net


def blocks(lines: list[str]) -> dict[str, list[str]]:
    """Config as {top-level line: [that line and its indented lines]}."""
    out: dict[str, list[str]] = {}
    for line in lines:
        if line.startswith(" ") and out:
            out[next(reversed(out))].append(line)
        elif line != "!":
            out[line] = [line]
    return out


def rename(line: str) -> str:
    for old, new in PORTS.items():
        line = line.replace(old, new)
    return line


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()
factory = blocks(pktlib.new(seed=0).router("FACTORY", OLD).running_config)

for old in [d for d in net if d.model == OLD]:
    name, xy = old.name, old.xy
    # (my port, the far end, whether my end is the serial DCE)
    cables = [
        (port.name, link.other(port), link.dce is not None and link.dce.device == name)
        for link in old.links
        for port in link.ports
        if port.device == old
    ]
    pings = [p for p in net.pdus if name in (p.source, p.destination)]
    # what was added or changed since the router left the factory, renamed for the new ports
    changed = [line for top, block in blocks(old.running_config).items() if factory.get(top) != block for line in block]
    changed = [rename(line) for line in changed if not line.startswith(("version", "hostname", "license", "end"))]

    net.remove_device(old)  # takes its cables and ping checks with it
    new = net.router(name, NEW, at=xy)
    for card, slot in CARDS:
        new.add_module(card, slot=slot)
    for port, peer, dce in cables:
        if dce:
            new[PORTS[port]].connect(peer)  # connect() from the DCE end
        else:
            peer.connect(new[PORTS[port]])
    new.config(changed)
    for p in pings:
        net.ping(p.source, p.destination, ip=p.ip, scenario=p.scenario)
    print(f"{name}: {OLD} -> {NEW}, {len(cables)} cables, {len(changed)} config lines, {len(pings)} ping checks")

net.save("swapped.pkt")
problems = pktlib.audit(net)
print("wrote swapped.pkt;", "audit: nothing found" if not problems else f"audit: {problems}")
