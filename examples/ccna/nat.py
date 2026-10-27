"""NAT three ways on one edge router: static NAT for a server, a dynamic pool, and PAT (overload).

    uv run python examples/ccna/nat.py        # writes nat.pkt

EDGE joins two private LANs to the ISP. The ISP knows only public addresses:
it routes 203.0.113.0/24 (the company's public block) to EDGE and has no route
to 192.168.0.0/16, so nothing private gets out untranslated.

  static   WEB (192.168.1.100) is always 203.0.113.10, so the internet can
           reach it: `ip nat inside source static`
  dynamic  the LAB LAN (192.168.2.0/24, access-list 2) borrows addresses
           from the pool 203.0.113.20 to .29, one per host
  PAT      the OFFICE LAN (192.168.1.0/24, access-list 1) shares EDGE's
           own outside address, told apart by port: `overload`

Gi0/0 and Gi0/2 are `ip nat inside`, Gi0/1 is `ip nat outside`.

Check in Packet Tracer:
  - OFFICE1 `ping 8.8.8.8`, then EDGE `show ip nat translations`: icmp
    entries with inside global 198.51.100.2 (PAT), and the static
    203.0.113.10 to 192.168.1.100
  - LAB1 `ping 8.8.8.8`: a translation to 203.0.113.20 (dynamic pool)
  - OUTSIDE `ping 203.0.113.10` reaches WEB through the static entry;
    OUTSIDE `ping 192.168.1.100` fails (no route to a private address)
  - EDGE `show ip nat statistics`: hits and misses, inside and outside
    interfaces
"""

import pktlib

net = pktlib.new()
isp = net.router("ISP", "2911", at=(800, 150))
edge = net.router("EDGE", "2911", at=(450, 150))
outside = net.server("OUTSIDE", at=(1050, 150), ip="8.8.8.8/24", gateway="8.8.8.1")

isp["g0/0"].connect(outside["fa0"])
isp["g0/0"].address = "8.8.8.1/24"
isp["g0/1"].connect(edge["g0/1"])
isp["g0/1"].address = "198.51.100.1/30"
edge["g0/1"].address = "198.51.100.2/30"
isp.config("ip route 203.0.113.0 255.255.255.0 198.51.100.2")

# inside: OFFICE on Gi0/0 (PAT, plus the static web server), LAB on Gi0/2 (dynamic pool)
LANS = {"OFFICE": ("g0/0", 1, 200), "LAB": ("g0/2", 2, 650)}
for name, (port, n, x) in LANS.items():
    sw = net.switch(f"{name}-SW", at=(x, 320))
    edge[port].connect(sw["g0/1"])
    edge[port].address = f"192.168.{n}.1/24"
    for i in (1, 2):
        pc = net.pc(f"{name}{i}", at=(x - 80 + 160 * (i - 1), 460), ip=f"192.168.{n}.1{i}/24", gateway=f"192.168.{n}.1")
        sw[f"fa0/{i}"].connect(pc["fa0"])
web = net.server("WEB", at=(120, 320), ip="192.168.1.100/24", gateway="192.168.1.1")
net["OFFICE-SW"]["fa0/3"].connect(web["fa0"])

edge.config("""
interface g0/0
 ip nat inside
interface g0/2
 ip nat inside
interface g0/1
 ip nat outside
ip route 0.0.0.0 0.0.0.0 198.51.100.1
access-list 1 permit 192.168.1.0 0.0.0.255
access-list 2 permit 192.168.2.0 0.0.0.255
ip nat pool LAB-POOL 203.0.113.20 203.0.113.29 netmask 255.255.255.0
ip nat inside source static 192.168.1.100 203.0.113.10
ip nat inside source list 2 pool LAB-POOL
ip nat inside source list 1 interface GigabitEthernet0/1 overload
""")

net.around(
    "OFFICE-SW", "OFFICE1", "OFFICE2", web, shape="rectangle", outline="blue", label="OFFICE: PAT, WEB static", pad=30
)
net.around("LAB-SW", "LAB1", "LAB2", shape="rectangle", outline="green", label="LAB: dynamic pool", pad=30)
net.around(isp, outside, shape="rectangle", outline="grey", label="INTERNET: public addresses only", pad=30)
net.note("inside: Gi0/0, Gi0/2\noutside: Gi0/1", at=(380, 60))

net.ping("OFFICE1", "OUTSIDE", scenario="Office out through PAT")
net.ping("LAB2", "OUTSIDE", scenario="Lab out through the dynamic pool")
net.ping("OUTSIDE", "WEB", ip="203.0.113.10", scenario="Internet to WEB through static NAT")
net.ping("OUTSIDE", "WEB", ip="192.168.1.100", scenario="Internet to a private address: should FAIL")

net.save("nat.pkt")
print(f"nat.pkt: {len(net.devices)} devices, {len(net.links)} links")
