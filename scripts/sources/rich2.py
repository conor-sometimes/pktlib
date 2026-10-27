"""Build the answer and start networks behind tests/fixtures/rich2.pka.

    uv run python scripts/sources/rich2.py        # writes rich2-answer.pkt and rich2-start.pkt here

The fixtures in tests/fixtures/ are these two files opened and saved again by
Packet Tracer 8.2 (their RECENT_FILES lists emptied); rich2.pka was made from them
in the Activity Wizard, to learn how it stores DHCP, routes, ACLs and NAT.

R1 (a 2911) is the edge router for one LAN:
  DHCP     pool LAN for 192.168.1.0/24 (default-router, dns-server), excluded .1-.20
  routes   a default route and a static route to 10.20.0.0/16, both via ISP
  ACLs     standard 20 out on Gi0/0: nothing from 9.9.9.9 reaches the LAN
           extended 110 in on Gi0/0: the LAN can't ping 8.8.4.4
  NAT      PAT (overload) on Gi0/1 for access-list 1; static NAT SERVER
           192.168.1.10 = 203.0.113.10
ISP has loopbacks 8.8.8.8, 8.8.4.4 and 9.9.9.9 and routes 203.0.113.0/24 to R1.
PC1 and PC2 use DHCP; SERVER is static. The start network has the same devices,
cables and ISP, and R1 blank.

Check in Packet Tracer: PC1 and PC2 lease .21 and up; PC1 pings 8.8.8.8 (through
PAT) but not 8.8.4.4 (ACL 110) or 9.9.9.9 (ACL 20 drops the replies); ISP pings
203.0.113.10 (the static NAT to SERVER).
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent

R1_CONFIG = """
hostname R1
ip dhcp excluded-address 192.168.1.1 192.168.1.20
ip dhcp pool LAN
 network 192.168.1.0 255.255.255.0
 default-router 192.168.1.1
 dns-server 8.8.8.8
interface GigabitEthernet0/0
 ip address 192.168.1.1 255.255.255.0
 ip nat inside
 ip access-group 110 in
 ip access-group 20 out
 no shutdown
interface GigabitEthernet0/1
 ip address 198.51.100.2 255.255.255.252
 ip nat outside
 no shutdown
ip route 0.0.0.0 0.0.0.0 198.51.100.1
ip route 10.20.0.0 255.255.0.0 198.51.100.1
access-list 1 permit 192.168.1.0 0.0.0.255
access-list 20 deny host 9.9.9.9
access-list 20 permit any
access-list 110 deny icmp 192.168.1.0 0.0.0.255 host 8.8.4.4
access-list 110 permit ip any any
ip nat inside source list 1 interface GigabitEthernet0/1 overload
ip nat inside source static 192.168.1.10 203.0.113.10
"""


def build(done: bool) -> pktlib.Network:
    net = pktlib.new(seed=72)
    r1 = net.router("R1", "2911", at=(400, 150))
    isp = net.router("ISP", "2911", at=(700, 150))
    sw = net.switch("SW1", at=(400, 300))
    pcs = [net.pc(f"PC{i}", at=(250 + 150 * (i - 1), 450)) for i in (1, 2)]
    server = net.server("SERVER", at=(550, 450), ip="192.168.1.10/24", gateway="192.168.1.1")
    r1["g0/0"].connect(sw["g0/1"])
    r1["g0/1"].connect(isp["g0/0"])
    for i, pc in enumerate(pcs, 1):
        pc.use_dhcp()
        pc["fa0"].connect(sw[f"fa0/{i}"])
    server["fa0"].connect(sw["fa0/3"])
    isp.config("""
interface GigabitEthernet0/0
 ip address 198.51.100.1 255.255.255.252
 no shutdown
interface Loopback0
 ip address 8.8.8.8 255.255.255.255
interface Loopback1
 ip address 8.8.4.4 255.255.255.255
interface Loopback2
 ip address 9.9.9.9 255.255.255.255
ip route 203.0.113.0 255.255.255.0 198.51.100.2
""")
    if done:
        r1.config(R1_CONFIG)
    return net


if __name__ == "__main__":
    for done, name in ((True, "rich2-answer.pkt"), (False, "rich2-start.pkt")):
        net = build(done)
        net.save(HERE / name)
        print("wrote", HERE / name, pktlib.audit(net) or "audit: clean")
