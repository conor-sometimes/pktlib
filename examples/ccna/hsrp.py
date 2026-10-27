"""HSRP: two routers share one virtual gateway address, so the LAN survives losing either.

    uv run python examples/ccna/hsrp.py        # writes hsrp.pkt

R1 (192.168.1.2) and R2 (192.168.1.3) both sit on the office LAN and run
HSRP group 1 with the virtual address 192.168.1.1, which is every PC's
default gateway. R1 has priority 110 and R2 the default 100, so R1 is active
and answers for the virtual IP and MAC (0000.0c07.ac01); R2 is standby.
`preempt` on R1 lets it take the role back when it recovers. Both routers
reach the ISP over their own links, with OSPF between the three routers.

Check in Packet Tracer:
  - R1 `show standby brief`: Gi0/0 group 1, priority 110, P, Active,
    virtual IP 192.168.1.1; R2 shows Standby
  - PC1 `arp -a` after a ping out: 192.168.1.1 is 0000.0c07.ac01
  - PC1 `tracert 8.8.8.8`: the first hop is 192.168.1.2 (R1)
  - On R1 `interface g0/0`, `shutdown`: R2 `show standby brief` turns
    Active within about 10 s, and PC1 `ping 8.8.8.8` works again;
    `no shutdown` and R1 takes over again (preempt)
"""

import pktlib

net = pktlib.new()
isp = net.router("ISP", "2911", at=(500, 60))
server = net.server("INTERNET", at=(800, 60), ip="8.8.8.8/24", gateway="8.8.8.1")
r1 = net.router("R1", "2911", at=(300, 220))
r2 = net.router("R2", "2911", at=(700, 220))
sw = net.switch("SW1", at=(500, 360))

isp["g0/2"].connect(server["fa0"])
isp["g0/2"].address = "8.8.8.1/24"
isp.config("router ospf 1\n router-id 9.9.9.9\n network 8.8.8.0 0.0.0.255 area 0\n network 10.0.0.0 0.0.0.7 area 0")

for n, r in ((1, r1), (2, r2)):
    isp[f"g0/{n - 1}"].connect(r["g0/1"])
    sub = 4 * (n - 1)
    isp[f"g0/{n - 1}"].address = f"10.0.0.{sub + 1}/30"
    r["g0/1"].address = f"10.0.0.{sub + 2}/30"
    r["g0/0"].connect(sw[f"g0/{n}"])
    r["g0/0"].address = f"192.168.1.{n + 1}/24"
    r.config(f"""
interface g0/0
 standby 1 ip 192.168.1.1
router ospf 1
 router-id {n}.{n}.{n}.{n}
 network 10.0.0.{sub} 0.0.0.3 area 0
 network 192.168.1.0 0.0.0.255 area 0
""")
r1.config("interface g0/0\n standby 1 priority 110\n standby 1 preempt")

for i in range(3):
    pc = net.pc(f"PC{i + 1}", at=(350 + 150 * i, 500), ip=f"192.168.1.{10 + i}/24", gateway="192.168.1.1")
    sw[f"fa0/{i + 1}"].connect(pc["fa0"])

net.around(r1, r2, shape="ellipse", outline="blue", label="HSRP group 1, virtual 192.168.1.1", pad=40)
net.note("R1 priority 110: active", at=(150, 280))
net.note("R2 priority 100: standby", at=(760, 280))

net.ping("PC1", "INTERNET", scenario="Out through the HSRP gateway")
net.ping("PC3", "INTERNET", scenario="Out through the HSRP gateway")
net.ping("PC2", "R1", ip="192.168.1.1", scenario="The virtual gateway answers")

net.save("hsrp.pkt")
print(f"hsrp.pkt: {len(net.devices)} devices, {len(net.links)} links")
