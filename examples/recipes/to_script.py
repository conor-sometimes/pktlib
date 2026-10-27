"""Turn any .pkt into a Python script that rebuilds it, then check the rebuild matches.

    uv run python examples/recipes/to_script.py              # sample.pkt -> rebuild_sample.py
    uv run python examples/recipes/to_script.py lab.pkt      # lab.pkt -> rebuild_lab.py

Shows: `pktlib.to_python(net, out=...)`, the same as `pktlib dump lab.pkt`.
The script is a starting point: edit it, add a router, put it in a loop.
Here it is also run (with `exec`, keeping the network it builds) and the
result compared with the original, device by device, so you can see what
came across.
"""

import sys
from pathlib import Path

import pktlib


def sample() -> pktlib.Network:
    """Two routers on a serial link with OSPF, a LAN on each."""
    net = pktlib.new(seed=11)
    r1 = net.router("R1", "1841+WIC-2T", at=(200, 150))
    r2 = net.router("R2", "1841+WIC-2T", at=(500, 150))
    r1["se0/0/0"].connect(r2["se0/0/0"])
    r1["se0/0/0"].address = "10.0.0.1/30"
    r2["se0/0/0"].address = "10.0.0.2/30"
    for n, r in ((1, r1), (2, r2)):
        pc = net.pc(f"PC{n}", at=(r.xy[0], 300), ip=f"192.168.{n}.10/24", gateway=f"192.168.{n}.1")
        r["fa0/0"].connect(pc["fa0"])
        r["fa0/0"].address = f"192.168.{n}.1/24"
        r.config(f"router ospf 1\n network 10.0.0.0 0.0.0.3 area 0\n network 192.168.{n}.0 0.0.0.255 area 0")
    net.ping("PC1", "PC2", scenario="Across the serial link")
    net.save("sample.pkt")
    return net


path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample.pkt")
original = pktlib.load(path) if len(sys.argv) > 1 else sample()

script = Path(f"rebuild_{path.stem}.py")
source = pktlib.to_python(original, out=f"rebuilt_{path.stem}.pkt")
script.write_text(source)
print(f"wrote {script} ({len(source.splitlines())} lines); run it to get rebuilt_{path.stem}.pkt")

# run the script here and keep its network, to see what came across
scope: dict = {}
exec(compile(source, str(script), "exec"), scope)
rebuilt: pktlib.Network = scope["net"]


def summary(net: pktlib.Network) -> dict[str, object]:
    return {
        "devices": sorted((d.name, d.model) for d in net),
        "cables": sorted(sorted(f"{e.device} {e.port}" for e in link.ends) for link in net.links),
        "addresses": sorted((d.name, p.name, p.address) for d in net for p in d if p.address),
        "config": {d.name: d.running_config for d in net if d.has_ios},
        "VLANs": {d.name: dict(d.vlans) for d in net if d.kind in ("Switch", "MultiLayerSwitch")},
        "DHCP hosts": sorted(d.name for d in net if not d.has_ios and d.dhcp),
        "ping checks": sorted(net.pdus),
    }


before, after = summary(original), summary(rebuilt)
for what in before:
    print(f"  {what:12} {'same' if before[what] == after[what] else 'DIFFERENT'}")
