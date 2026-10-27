"""DHCP from a router: a local pool for its own LAN, and a relayed pool for a branch LAN with `ip helper-address`.

    uv run python examples/ccna/dhcp.py        # writes dhcp.pkt

HQ (a 2911) is the DHCP server for two LANs:

  HQ-LAN      192.168.10.0/24, on HQ's own Gi0/0: clients broadcast and HQ
              answers directly
  BRANCH-LAN  192.168.20.0/24, behind BRANCH. A DHCP Discover is a
              broadcast and routers don't forward broadcasts, so BRANCH's LAN
              port has `ip helper-address 10.0.0.1`: BRANCH relays the request
              to HQ as unicast, and HQ picks the pool from the relay's address

Each pool hands out a default router and a DNS server, and `ip dhcp
excluded-address` keeps .1 to .10 back for static devices (the routers, the
server, the printer). Every PC is a DHCP client.

Check in Packet Tracer:
  - HQ-PC1 and BRANCH-PC1 Desktop > IP Configuration: DHCP gives
    192.168.10.11 and up, and 192.168.20.11 and up, with the right gateway
    and DNS 192.168.10.5
  - HQ `show ip dhcp binding`: four bindings, two from each pool
  - HQ `show ip dhcp pool`: leased addresses counted per pool
  - BRANCH `show running-config interface g0/0`: ip helper-address 10.0.0.1
  - BRANCH-PC2 `ping 192.168.10.5` (the server at HQ)
"""

import pktlib

net = pktlib.new()
hq = net.router("HQ", "2911", at=(300, 150))
branch = net.router("BRANCH", "2911", at=(750, 150))
hq["g0/1"].connect(branch["g0/1"])
hq["g0/1"].address = "10.0.0.1/30"
branch["g0/1"].address = "10.0.0.2/30"

for r, lan in ((hq, 10), (branch, 20)):
    sw = net.switch(f"{r.name}-SW", at=(r.xy[0], 300))
    r["g0/0"].connect(sw["g0/1"])
    r["g0/0"].address = f"192.168.{lan}.1/24"
    for i in (1, 2):
        pc = net.pc(f"{r.name}-PC{i}", at=(r.xy[0] - 160 + 110 * (i - 1), 450))
        pc.use_dhcp()
        sw[f"fa0/{i}"].connect(pc["fa0"])

server = net.server("SERVER", at=(hq.xy[0] + 110, 450), ip="192.168.10.5/24", gateway="192.168.10.1")
net["HQ-SW"]["fa0/3"].connect(server["fa0"])
printer = net.printer("PRINTER", at=(branch.xy[0] + 110, 450), ip="192.168.20.5/24", gateway="192.168.20.1")
net["BRANCH-SW"]["fa0/3"].connect(printer["fa0"])

hq.config("""
ip dhcp excluded-address 192.168.10.1 192.168.10.10
ip dhcp excluded-address 192.168.20.1 192.168.20.10
ip dhcp pool HQ-LAN
 network 192.168.10.0 255.255.255.0
 default-router 192.168.10.1
 dns-server 192.168.10.5
ip dhcp pool BRANCH-LAN
 network 192.168.20.0 255.255.255.0
 default-router 192.168.20.1
 dns-server 192.168.10.5
ip route 192.168.20.0 255.255.255.0 10.0.0.2
""")
branch.config("""
interface g0/0
 ip helper-address 10.0.0.1
ip route 0.0.0.0 0.0.0.0 10.0.0.1
""")

net.around(hq, "HQ-SW", "HQ-PC1", "HQ-PC2", server, shape="rectangle", outline="blue", label="HQ: DHCP server", pad=40)
net.around(
    branch,
    "BRANCH-SW",
    "BRANCH-PC1",
    "BRANCH-PC2",
    printer,
    shape="rectangle",
    outline="green",
    label="BRANCH: DHCP relay",
    pad=40,
)
net.note("ip helper-address 10.0.0.1", at=(560, 90))

net.ping("BRANCH-PC1", "SERVER", scenario="Relayed DHCP client to the HQ server")
net.ping("HQ-PC1", "PRINTER", scenario="Local DHCP client to the branch printer")
net.ping("BRANCH-PC2", "PRINTER", scenario="Relayed DHCP client on its own LAN")

net.save("dhcp.pkt")
print(f"dhcp.pkt: {len(net.devices)} devices, {len(net.links)} links")
