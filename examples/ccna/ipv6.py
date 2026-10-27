"""IPv6 next to IPv4: global and link-local addresses, OSPFv3 between two routers, static routes to a stub branch.

    uv run python examples/ccna/ipv6.py        # writes ipv6.pkt

Three routers in a line, every link dual stack (an IPv4 and an IPv6 address
on each interface). `ipv6 unicast-routing` turns IPv6 routing on; pktlib
writes it ahead of the interfaces, where Packet Tracer needs it.

  R1, R2   OSPFv3 (`ipv6 router ospf 1`, then `ipv6 ospf 1 area 0` on each
           interface: OSPFv3 is enabled per interface, not with `network`),
           and OSPFv2 for IPv4 alongside it
  R3       a stub branch with no routing protocol: a static default route
           (`ipv6 route ::/0 ...`, `ip route 0.0.0.0 ...`) to R2
  R2       a static route to R3's LAN (2001:db8:acad:3::/64) via R3
  R1       the same route via R2; R2 advertises its link to R3 in OSPFv3,
           so R1 has a path toward that next hop too

Each router interface has a global unicast address in 2001:db8:acad::/48 and a
link-local address set by hand (fe80::1 on R1, fe80::2 on R2, fe80::3 on R3),
so neighbours and next hops are easy to read.

The PCs are given IPv4 addresses (pktlib sets only IPv4 on end devices), so
the ping scenarios are IPv4. For IPv6 on a PC, set Desktop > IP Configuration
> IPv6 to Automatic: the router's advertisements give it a SLAAC address.

Check in Packet Tracer:
  - R1 `show ipv6 interface brief`: each port with its fe80:: and 2001:db8: address
  - R1 `show ipv6 ospf neighbor`: 2.2.2.2 FULL on Gi0/1
  - R1 `show ipv6 route`: O 2001:db8:acad:2::/64 and O 2001:db8:acad:23::/64
    (OSPFv3), S 2001:db8:acad:3::/64 (static)
  - R3 `show ipv6 route`: S ::/0 via 2001:db8:acad:23::2
  - R1 `ping 2001:db8:acad:3::1`: R3's LAN over OSPFv3 and the statics
  - PC1 IPv6 set to Automatic, then `ping 2001:db8:acad:3::1`
"""

import pktlib

net = pktlib.new()
routers = [net.router(f"R{n}", "2911", at=(200 + 350 * (n - 1), 200)) for n in (1, 2, 3)]
r1, r2, r3 = routers
for r in routers:
    r.config("ipv6 unicast-routing")


def addr(r, port, v4, v6):
    """Both families on one port: IPv4 a.b.c.d/nn and IPv6 prefix::host/64, plus the router's link-local."""
    r[port].address = v4
    n = r.name[1]
    r.config(f"interface {port}\n ipv6 address {v6}/64\n ipv6 address fe80::{n} link-local")


# links: R1 g0/1 to R2 g0/1 (12), R2 g0/2 to R3 g0/2 (23)
r1["g0/1"].connect(r2["g0/1"])
addr(r1, "g0/1", "10.0.12.1/30", "2001:db8:acad:12::1")
addr(r2, "g0/1", "10.0.12.2/30", "2001:db8:acad:12::2")
r2["g0/2"].connect(r3["g0/2"])
addr(r2, "g0/2", "10.0.23.2/30", "2001:db8:acad:23::2")
addr(r3, "g0/2", "10.0.23.1/30", "2001:db8:acad:23::3")

# a LAN with one PC on each router
for n, r in enumerate(routers, 1):
    addr(r, "g0/0", f"192.168.{n}.1/24", f"2001:db8:acad:{n}::1")
    pc = net.pc(f"PC{n}", at=(r.xy[0], 380), ip=f"192.168.{n}.10/24", gateway=f"192.168.{n}.1")
    r["g0/0"].connect(pc["fa0"])

# R1 and R2: OSPFv3 for IPv6 and OSPFv2 for IPv4
for n, r, ports in ((1, r1, ("g0/0", "g0/1")), (2, r2, ("g0/0", "g0/1", "g0/2"))):
    rid = f"{n}.{n}.{n}.{n}"
    r.config(f"ipv6 router ospf 1\n router-id {rid}\nrouter ospf 1\n router-id {rid}")
    for p in ports:
        r.config(f"interface {p}\n ipv6 ospf 1 area 0")
r1.config("router ospf 1\n network 192.168.1.0 0.0.0.255 area 0\n network 10.0.12.0 0.0.0.3 area 0")
r2.config(
    "router ospf 1\n network 192.168.2.0 0.0.0.255 area 0\n network 10.0.12.0 0.0.0.3 area 0\n"
    " network 10.0.23.0 0.0.0.3 area 0"
)

# the stub branch: static routes both ways
r1.config("ipv6 route 2001:db8:acad:3::/64 2001:db8:acad:12::2\nip route 192.168.3.0 255.255.255.0 10.0.12.2")
r3.config("ipv6 route ::/0 2001:db8:acad:23::2\nip route 0.0.0.0 0.0.0.0 10.0.23.2")
r2.config("ipv6 route 2001:db8:acad:3::/64 2001:db8:acad:23::3\nip route 192.168.3.0 255.255.255.0 10.0.23.1")

net.around(r1, r2, shape="ellipse", outline="blue", label="OSPFv3 + OSPFv2 area 0", pad=40)
net.around(r3, "PC3", shape="ellipse", outline="green", label="stub branch: static routes", pad=40)
net.note("2001:db8:acad:12::/64", at=(330, 150))
net.note("2001:db8:acad:23::/64", at=(680, 150))

net.ping("PC1", "PC3", scenario="Across OSPF and the static routes")
net.ping("PC3", "PC2", scenario="Branch default route to R2")
net.ping("PC2", "PC1", scenario="Across OSPF")

net.save("ipv6.pkt")
print(f"ipv6.pkt: {len(net.devices)} devices, {len(net.links)} links")
