"""Three routers in a line running RIPv2, with discontiguous subnets that need no auto-summary.

    uv run python examples/ccna/ripv2.py        # writes ripv2.pkt

R1 and R3 each have a LAN cut from 172.16.0.0/16, but R2 in the middle only
has 10.0.0.0 links, so 172.16.0.0 is discontiguous. RIP version 1, or version
2 with auto-summary on, would advertise both LANs as the classful
172.16.0.0/16 and R2 could not tell them apart. Here every router runs
`version 2` with `no auto-summary`, so the /24s go out as they are. The LAN
ports are passive: no RIP updates are sent to the PCs.

Check in Packet Tracer:
  - R1 `show ip protocols`: Routing Protocol is "rip", version 2 sent and
    received, automatic network summarization not in effect, Fa0/0 passive
  - R2 `show ip route rip`: R 172.16.1.0/24 [120/1] and R 172.16.3.0/24
    [120/1], two separate /24s (no 172.16.0.0/16 summary)
  - R1 `show ip route rip`: R 172.16.3.0/24 [120/2] via 10.0.0.2 (two hops)
  - PC1 `tracert 172.16.3.10`: three hops, R1, R2, R3
"""

import pktlib

net = pktlib.new()

routers = [net.router(f"R{i}", "1841+WIC-2T", at=(250 + 300 * (i - 1), 250)) for i in (1, 2, 3)]
r1, r2, r3 = routers

# the serial chain: R1 se0/0/0 (DCE) to R2 se0/0/0, R2 se0/0/1 (DCE) to R3 se0/0/1
r1["se0/0/0"].connect(r2["se0/0/0"])
r1["se0/0/0"].address = "10.0.0.1/30"
r2["se0/0/0"].address = "10.0.0.2/30"
r2["se0/0/1"].connect(r3["se0/0/1"])
r2["se0/0/1"].address = "10.0.0.5/30"
r3["se0/0/1"].address = "10.0.0.6/30"
r1.config("interface se0/0/0\n clock rate 64000")
r2.config("interface se0/0/1\n clock rate 64000")

# a LAN on each end router, and a loopback on R2 so it has something of its own to advertise
for r, lan, x in ((r1, "172.16.1", 100), (r3, "172.16.3", 850)):
    sw = net.switch(f"SW-{r.name}", at=(x, 400))
    r["fa0/0"].connect(sw["fa0/1"])
    r["fa0/0"].address = f"{lan}.1/24"
    for j in (1, 2):
        pc = net.pc(f"PC{r.name[1]}-{j}", at=(x - 80 + 160 * (j - 1), 530), ip=f"{lan}.{9 + j}/24", gateway=f"{lan}.1")
        sw[f"fa0/{j + 1}"].connect(pc["fa0"])
    r.config("""
router rip
 version 2
 no auto-summary
 network 10.0.0.0
 network 172.16.0.0
 passive-interface FastEthernet0/0
""")
r2.config("""
interface loopback 0
 ip address 192.168.2.1 255.255.255.0
router rip
 version 2
 no auto-summary
 network 10.0.0.0
 network 192.168.2.0
""")

net.around(*routers, shape="ellipse", outline="orange", label="RIPv2, no auto-summary", pad=50)
net.note("172.16.1.0/24", at=(40, 600))
net.note("172.16.3.0/24", at=(800, 600))
net.note("10.0.0.0/30 links: 172.16.0.0 is discontiguous", at=(380, 330))

net.ping("PC1-1", "PC3-1", scenario="Across RIP, LAN to LAN")
net.ping("PC3-2", "R2", ip="192.168.2.1", scenario="To R2 loopback")
net.ping("PC1-2", "PC3-2", scenario="Across RIP, LAN to LAN")

net.save("ripv2.pkt")
print(f"ripv2.pkt: {len(net.devices)} devices, {len(net.links)} links")
