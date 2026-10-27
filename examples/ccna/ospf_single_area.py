"""Single-area OSPF on a triangle of routers, with router IDs, passive LANs and a default route.

    uv run python examples/ccna/ospf_single_area.py        # writes ospf_single_area.pkt

Three 2911s in a triangle of gigabit links, all in area 0. Each has a LAN
with two PCs. What the config shows:

  - `router-id` set by hand (1.1.1.1, 2.2.2.2, 3.3.3.3), so `show ip ospf
    neighbor` is easy to read
  - `network` statements with wildcard masks, one per subnet
  - `passive-interface` on the LAN ports: the LAN is advertised but no hellos
    are sent to the PCs
  - R1 has a static default route to the ISP and `default-information
    originate`, so R2 and R3 learn O*E2 0.0.0.0/0 from OSPF

Check in Packet Tracer:
  - R1 `show ip ospf neighbor`: 2.2.2.2 and 3.3.3.3, both FULL
  - R2 `show ip route ospf`: O 192.168.1.0/24, O 192.168.3.0/24 and
    O*E2 0.0.0.0/0 via R1
  - R2 `show ip protocols`: Router ID 2.2.2.2, GigabitEthernet0/0 passive
  - PC2-1 `ping 8.8.8.8`: works through R1 and the default route
  - On R1 `interface g0/1`, `shutdown`: R2 `show ip route ospf` now reaches
    192.168.1.0/24 through R3, and the pings still work
"""

import pktlib

net = pktlib.new()

r1 = net.router("R1", "2911", at=(500, 200))
r2 = net.router("R2", "2911", at=(300, 420))
r3 = net.router("R3", "2911", at=(700, 420))
RID = {r1: "1.1.1.1", r2: "2.2.2.2", r3: "3.3.3.3"}

# the triangle: g0/1 and g0/2 on each router
TRIANGLE = [
    (r1, "g0/1", r2, "g0/1", "10.0.12"),
    (r1, "g0/2", r3, "g0/1", "10.0.13"),
    (r2, "g0/2", r3, "g0/2", "10.0.23"),
]
for a, ap, b, bp, sub in TRIANGLE:
    a[ap].connect(b[bp])
    a[ap].address = f"{sub}.1/30"
    b[bp].address = f"{sub}.2/30"
    for r in (a, b):
        r.config(f"router ospf 1\n network {sub}.0 0.0.0.3 area 0")

# a LAN on g0/0 of each router; R1's LAN switch sits above it, the others below
LAN_XY = {r1: (500, 60), r2: (150, 560), r3: (850, 560)}
for n, r in enumerate((r1, r2, r3), 1):
    x, y = LAN_XY[r]
    sw = net.switch(f"SW{n}", at=(x, y))
    r["g0/0"].connect(sw["fa0/1"])
    r["g0/0"].address = f"192.168.{n}.1/24"
    for j in (1, 2):
        side = -1 if r is r2 else 1
        pc = net.pc(
            f"PC{n}-{j}",
            at=(x + side * 140, y - 50 + 90 * (j - 1)),
            ip=f"192.168.{n}.{9 + j}/24",
            gateway=f"192.168.{n}.1",
        )
        sw[f"fa0/{j + 1}"].connect(pc["fa0"])
    r.config(f"""
router ospf 1
 router-id {RID[r]}
 network 192.168.{n}.0 0.0.0.255 area 0
 passive-interface GigabitEthernet0/0
""")

# R1's way out: an ISP with a server, and a default route that OSPF hands on
# (a 2911 has three gigabit ports, all used, so R1 gets an HWIC-2T for a serial link)
r1.add_module("HWIC-2T")  # Serial0/0/0, 0/0/1
isp = net.router("ISP", "1841+WIC-2T", at=(850, 200))
server = net.server("INTERNET", at=(1050, 200), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["fa0/0"].connect(server["fa0"])
isp["fa0/0"].address = "8.8.8.1/24"
isp["se0/0/0"].connect(r1["se0/0/0"])
isp["se0/0/0"].address = "203.0.113.1/30"
r1["se0/0/0"].address = "203.0.113.2/30"
isp.config("interface se0/0/0\n clock rate 64000\nip route 192.168.0.0 255.255.0.0 203.0.113.2")
r1.config("ip route 0.0.0.0 0.0.0.0 203.0.113.1\nrouter ospf 1\n default-information originate")

net.around(r1, r2, r3, shape="ellipse", outline="blue", label="OSPF area 0", pad=50)
net.around(isp, server, shape="rectangle", outline="grey", label="ISP (static routes only)", pad=30)

net.ping("PC2-1", "PC3-1", scenario="Across OSPF area 0")
net.ping("PC3-2", "PC1-2", scenario="Across OSPF area 0")
net.ping("PC2-1", "INTERNET", scenario="Default route learned from OSPF")
net.ping("PC3-1", "INTERNET", scenario="Default route learned from OSPF")

net.save("ospf_single_area.pkt")
print(f"ospf_single_area.pkt: {len(net.devices)} devices, {len(net.links)} links")
