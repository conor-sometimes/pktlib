"""Multi-area OSPF: a backbone with two area border routers, each leading to its own area.

    uv run python examples/ccna/ospf_multi_area.py        # writes ospf_multi_area.pkt

  area 0  CORE, ABR1 and ABR2 in a triangle (two Ethernet links and one
          serial), plus CORE's LAN
  area 1  ABR1's serial link to BRANCH1, and BRANCH1's LAN
  area 2  ABR2's serial link to BRANCH2, and BRANCH2's LAN

ABR1 and ABR2 have interfaces in two areas, so they are area border routers:
they hold one link-state database per area and pass routes between areas as
summary (type 3) LSAs. Routes from another area show as O IA in the routing
table. Every area touches area 0, as OSPF requires.

Check in Packet Tracer:
  - ABR1 `show ip ospf`: "It is an area border router", with Area BACKBONE(0)
    and Area 1 listed
  - BRANCH1 `show ip route ospf`: O IA 192.168.20.0/24 (area 2) and
    O IA 192.168.0.0/24 (CORE's LAN), learned from another area
  - BRANCH1 `show ip ospf database`: Summary Net Link States from 1.1.1.1
  - CORE `show ip ospf neighbor`: 1.1.1.1 and 2.2.2.2 FULL
  - PC-BRANCH1 `ping 192.168.20.10` (PC-BRANCH2): area 1 to area 2 through the backbone
"""

import pktlib

net = pktlib.new()

core = net.router("CORE", "2911", at=(500, 150))
abr1 = net.router("ABR1", "1841+WIC-2T", at=(300, 300))
abr2 = net.router("ABR2", "1841+WIC-2T", at=(700, 300))
br1 = net.router("BRANCH1", "1841+WIC-2T", at=(300, 500))
br2 = net.router("BRANCH2", "1841+WIC-2T", at=(700, 500))
RID = {core: "9.9.9.9", abr1: "1.1.1.1", abr2: "2.2.2.2", br1: "11.11.11.11", br2: "22.22.22.22"}
for r, rid in RID.items():
    r.config(f"router ospf 1\n router-id {rid}")


def link(a, ap, b, bp, sub, area):
    """Cable a.ap to b.bp, address .1 and .2 of a /30, both ends in `area`."""
    a[ap].connect(b[bp])
    a[ap].address = f"{sub}.1/30"
    b[bp].address = f"{sub}.2/30"
    if a[ap].link.cable == "serial":
        a.config(f"interface {a[ap].name}\n clock rate 64000")
    for r in (a, b):
        r.config(f"router ospf 1\n network {sub}.0 0.0.0.3 area {area}")


# area 0: the backbone triangle
link(core, "g0/1", abr1, "fa0/1", "10.0.0", 0)
link(core, "g0/2", abr2, "fa0/1", "10.0.1", 0)
link(abr1, "se0/0/1", abr2, "se0/0/1", "10.0.2", 0)
# areas 1 and 2: one serial link each
link(abr1, "se0/0/0", br1, "se0/0/0", "10.1.0", 1)
link(abr2, "se0/0/0", br2, "se0/0/0", "10.2.0", 2)

# LANs: CORE's in area 0, each branch's in its own area
LANS = [
    (core, "g0/0", "192.168.0", 0, (500, 20)),
    (br1, "fa0/0", "192.168.10", 1, (300, 640)),
    (br2, "fa0/0", "192.168.20", 2, (700, 640)),
]
for r, port, lan, area, (x, y) in LANS:
    pc = net.pc(f"PC-{r.name}", at=(x, y), ip=f"{lan}.10/24", gateway=f"{lan}.1")
    r[port].connect(pc["fa0"])
    r[port].address = f"{lan}.1/24"
    r.config(f"router ospf 1\n network {lan}.0 0.0.0.255 area {area}\n passive-interface {r[port].name}")

net.around(core, abr1, abr2, "PC-CORE", shape="ellipse", outline="blue", label="AREA 0 (backbone)", pad=40)
net.around(br1, "PC-BRANCH1", shape="ellipse", outline="green", label="AREA 1", pad=40)
net.around(br2, "PC-BRANCH2", shape="ellipse", outline="orange", label="AREA 2", pad=40)

net.ping("PC-BRANCH1", "PC-BRANCH2", scenario="Across OSPF areas")
net.ping("PC-BRANCH2", "PC-CORE", scenario="Area 2 to the backbone")
net.ping("PC-BRANCH1", "PC-CORE", scenario="Area 1 to the backbone")

net.save("ospf_multi_area.pkt")
print(f"ospf_multi_area.pkt: {len(net.devices)} devices, {len(net.links)} links")
