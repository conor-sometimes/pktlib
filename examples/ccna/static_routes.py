"""Static routes, a default route and a floating static backup between two sites.

    uv run python examples/ccna/static_routes.py        # writes static_routes.pkt

HQ and BRANCH are joined twice: a FastEthernet link (the primary path) and a
serial link (the backup). No routing protocol runs anywhere; every path is
typed by hand:

  HQ      a static route to the branch LAN over the Ethernet link, the same
          route over serial with administrative distance 200 (a floating
          static: it stays out of the table until the primary goes), and a
          default route to the ISP
  BRANCH  a default route to HQ over Ethernet, and a floating default over
          serial (distance 200)
  ISP     one static route back to both sites (192.168.0.0/16)

Shut HQ's Fa0/1 and the floating routes take over; bring it back and they
step aside again.

Check in Packet Tracer:
  - HQ `show ip route`: S 192.168.2.0/24 [1/0] via 10.0.0.2 and
    S* 0.0.0.0/0 [1/0] via 203.0.113.1
  - BRANCH `show ip route static`: S* 0.0.0.0/0 [1/0] via 10.0.0.1
  - BRANCH-PC `ping 192.168.1.10` (HQ-PC) and `ping 8.8.8.8` (ISP's server)
  - HQ `interface fa0/1`, `shutdown`; then HQ `show ip route static`:
    S 192.168.2.0/24 [200/0] via 10.0.0.6, and BRANCH-PC `tracert 192.168.1.10`
    goes over the serial link (10.0.0.5)
"""

import pktlib

net = pktlib.new()

hq = net.router("HQ", "1841+WIC-2T", at=(400, 250))
branch = net.router("BRANCH", "1841+WIC-2T", at=(800, 250))
isp = net.router("ISP", "1841+WIC-2T", at=(400, 60))

# LANs
for r, lan, x in ((hq, 1, 250), (branch, 2, 950)):
    sw = net.switch(f"{r.name}-SW", at=(x, 400))
    pc = net.pc(f"{r.name}-PC", at=(x, 530), ip=f"192.168.{lan}.10/24", gateway=f"192.168.{lan}.1")
    r["fa0/0"].connect(sw["fa0/1"])
    sw["fa0/2"].connect(pc["fa0"])
    r["fa0/0"].address = f"192.168.{lan}.1/24"

# primary: Ethernet; backup: serial (HQ is the DCE end)
hq["fa0/1"].connect(branch["fa0/1"])
hq["fa0/1"].address = "10.0.0.1/30"
branch["fa0/1"].address = "10.0.0.2/30"
hq["se0/0/1"].connect(branch["se0/0/1"])
hq["se0/0/1"].address = "10.0.0.5/30"
branch["se0/0/1"].address = "10.0.0.6/30"
hq.config("interface se0/0/1\n clock rate 64000")

# the ISP and a server standing in for the internet
isp["se0/0/0"].connect(hq["se0/0/0"])
isp["se0/0/0"].address = "203.0.113.1/30"
hq["se0/0/0"].address = "203.0.113.2/30"
isp.config("interface se0/0/0\n clock rate 64000")
isp["fa0/0"].address = "8.8.8.1/24"
server = net.server("INTERNET", at=(650, 60), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["fa0/0"].connect(server["fa0"])

hq.config("""
ip route 192.168.2.0 255.255.255.0 10.0.0.2
ip route 192.168.2.0 255.255.255.0 10.0.0.6 200
ip route 0.0.0.0 0.0.0.0 203.0.113.1
""")
branch.config("""
ip route 0.0.0.0 0.0.0.0 10.0.0.1
ip route 0.0.0.0 0.0.0.0 10.0.0.5 200
""")
isp.config("ip route 192.168.0.0 255.255.0.0 203.0.113.2")

net.around(hq, "HQ-SW", "HQ-PC", shape="rectangle", outline="blue", label="HQ 192.168.1.0/24", pad=40)
net.around(branch, "BRANCH-SW", "BRANCH-PC", shape="rectangle", outline="green", label="BRANCH 192.168.2.0/24", pad=40)
net.around(isp, server, shape="rectangle", outline="grey", label="INTERNET", pad=30)
net.note("Fa0/1: primary (AD 1)\nSe0/0/1: floating backup (AD 200)", at=(520, 330))

net.ping("BRANCH-PC", "HQ-PC", scenario="Branch to HQ over static routes")
net.ping("BRANCH-PC", "INTERNET", scenario="Branch to internet over two default routes")
net.ping("HQ-PC", "INTERNET", scenario="HQ to internet over the default route")

net.save("static_routes.pkt")
print(f"static_routes.pkt: {len(net.devices)} devices, {len(net.links)} links")
