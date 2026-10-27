"""N routers in a serial ring running OSPF, each with its own LAN.

    uv run python examples/labs/ospf_ring.py            # 5 routers, 2 PCs each
    uv run python examples/labs/ospf_ring.py 8 3        # 8 routers, 3 PCs each

Every address is worked out with the ipaddress module, so changing N gives a
new, correctly numbered network. Open ospf_ring.pkt and ping across the ring.
"""

import ipaddress
import math
import sys

import pktlib

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
PCS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
lans = ipaddress.ip_network("10.0.0.0/16").subnets(new_prefix=24)
wans = ipaddress.ip_network("172.16.0.0/24").subnets(new_prefix=30)

net = pktlib.new()
cx, cy, radius = 700, 380, 230
routers = []
for i in range(N):
    a = 2 * math.pi * i / N - math.pi / 2
    x, y = cx + radius * math.cos(a), cy + radius * math.sin(a)
    r = net.router(f"R{i + 1}", "1841+WIC-2T", at=(round(x), round(y)))
    routers.append(r)

    # a LAN hanging off each router, pushed outward from the centre
    lan = next(lans)
    gw, *hosts = lan.hosts()
    ox, oy = math.cos(a), math.sin(a)
    sw = net.switch(f"SW{i + 1}", at=(round(x + 130 * ox), round(y + 130 * oy)))
    r["fa0/0"].connect(sw["fa0/1"])
    r["fa0/0"].address = f"{gw}/24"
    for j in range(PCS):
        side = (j - (PCS - 1) / 2) * 70
        px, py = x + 230 * ox - side * oy, y + 230 * oy + side * ox
        pc = net.pc(f"PC{i + 1}-{j + 1}", at=(round(px), round(py)), ip=f"{hosts[j]}/24", gateway=str(gw))
        sw[f"fa0/{j + 2}"].connect(pc["fa0"])
    r.config(f"router ospf 1\n network {lan.network_address} 0.0.0.255 area 0")

# the ring: R1 se0/0/0 (DCE) -> R2 se0/0/1, R2 se0/0/0 -> R3 se0/0/1, ... back to R1
for i, r in enumerate(routers):
    nxt = routers[(i + 1) % N]
    wan = next(wans)
    a, b = wan.hosts()
    r["se0/0/0"].connect(nxt["se0/0/1"])
    r["se0/0/0"].address = f"{a}/30"
    nxt["se0/0/1"].address = f"{b}/30"
    r.config(f"interface se0/0/0\n clock rate 64000\nrouter ospf 1\n network {wan.network_address} 0.0.0.3 area 0")
    nxt.config(f"router ospf 1\n network {wan.network_address} 0.0.0.3 area 0")

# ping checks, listed under the workspace: click one once OSPF has converged
net.ping("PC1-1", f"PC{N // 2 + 1}-1", scenario="Across the ring")
net.ping("PC1-1", f"PC{N}-1", scenario="To the next router back")
net.ping("PC1-1", "PC2-1", scenario="To the next router on")

net.save("ospf_ring.pkt")
print(f"ospf_ring.pkt: {len(net.devices)} devices, {len(net.links)} links")
