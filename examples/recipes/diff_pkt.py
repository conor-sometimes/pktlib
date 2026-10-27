"""Diff two .pkt files: devices, cables, addresses and config.

    uv run python examples/recipes/diff_pkt.py               # builds before.pkt and after.pkt, diffs them
    uv run python examples/recipes/diff_pkt.py starter.pkt handed_in.pkt

Shows: comparing two networks as plain Python sets and dicts (devices by name,
cables by their ends, addresses by interface), and `difflib` on each device's
`running_config`. Handy for "what did the student change?" or "what did my
script change?".
"""

import difflib
import sys

import pktlib


def sample() -> tuple[pktlib.Network, pktlib.Network]:
    """A starter file, and a copy someone has worked on."""
    before = pktlib.new(seed=3)
    r1 = before.router("R1", "1941", at=(300, 100))
    sw = before.switch("SW1", at=(300, 220))
    sw["g0/1"].connect(r1["g0/0"])
    r1["g0/0"].address = "192.168.1.1/24"
    for i in (1, 2):
        pc = before.pc(f"PC{i}", at=(200 * i, 340), ip=f"192.168.1.{10 + i}/24", gateway="192.168.1.1")
        sw[f"fa0/{i}"].connect(pc["fa0"])
    before.ping("PC1", "PC2", scenario="PC1 to PC2")
    before.save("before.pkt")

    after = pktlib.Network.from_bytes(before.to_bytes(), seed=4)  # a copy to change
    after["PC2"].set_ip("192.168.1.20/24", "192.168.1.1")  # readdressed
    pc3 = after.pc("PC3", at=(600, 340), ip="192.168.1.13/24", gateway="192.168.1.1")  # added
    after["SW1"]["fa0/3"].connect(pc3["fa0"])
    after["R1"].config("hostname GATEWAY\nrouter ospf 1\n network 192.168.1.0 0.0.0.255 area 0")  # configured
    after["SW1"].xy = (320, 220)  # moved
    after.ping("PC1", "PC3", scenario="PC1 to the new PC3")
    after.save("after.pkt")
    return before, after


def addresses(net: pktlib.Network) -> dict[str, str]:
    """'DEVICE interface' -> address, for every address in the network."""
    out = {}
    for d in net:
        if d.has_ios:
            out.update({f"{d.name} {n}": i.address for n, i in d.interfaces.items() if i.address})
        else:
            out.update({f"{d.name} {p.name}": p.address for p in d if p.address})
    return out


def cables(net: pktlib.Network) -> set[str]:
    """Each cable as one sorted string, so A-B and B-A compare equal."""
    return {" <-> ".join(sorted(f"{e.device} {e.port}" for e in link.ends)) for link in net.links}


if len(sys.argv) > 2:
    before, after = pktlib.load(sys.argv[1]), pktlib.load(sys.argv[2])
else:
    before, after = sample()

old, new = {d.name: d for d in before}, {d.name: d for d in after}
for name in sorted(old.keys() - new.keys()):
    print(f"- device {name} ({old[name].model})")
for name in sorted(new.keys() - old.keys()):
    print(f"+ device {name} ({new[name].model})")
for name in sorted(old.keys() & new.keys()):
    if old[name].model != new[name].model:
        print(f"~ device {name}: {old[name].model} -> {new[name].model}")
    if old[name].xy != new[name].xy:
        print(f"~ device {name} moved: {old[name].xy} -> {new[name].xy}")

for c in sorted(cables(before) - cables(after)):
    print(f"- cable {c}")
for c in sorted(cables(after) - cables(before)):
    print(f"+ cable {c}")

a, b = addresses(before), addresses(after)
for key in sorted(a.keys() | b.keys()):
    if a.get(key) != b.get(key):
        print(f"~ address {key}: {a.get(key, '(none)')} -> {b.get(key, '(none)')}")

for name in sorted(old.keys() & new.keys()):
    if old[name].has_ios and old[name].running_config != new[name].running_config:
        print(f"~ config {name}:")
        diff = difflib.unified_diff(old[name].running_config, new[name].running_config, lineterm="", n=0)
        for line in list(diff)[2:]:  # skip the ---/+++ header
            print(f"    {line}")
