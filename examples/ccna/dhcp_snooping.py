"""DHCP snooping: a rogue DHCP server on an access port is ignored, so clients get the real gateway.

    uv run python examples/ccna/dhcp_snooping.py        # writes dhcp_snooping.pkt

R1 is the real DHCP server for 192.168.1.0/24, on SW1's uplink Gi0/1. Someone
has plugged ROGUE, a router with its own DHCP pool, into an access port. Its
pool hands out a gateway (192.168.1.254) that leads nowhere, a classic way to
pull traffic through an attacker. Without protection a PC takes whichever
offer arrives first.

SW1 runs DHCP snooping on VLAN 1: `ip dhcp snooping`, `ip dhcp snooping vlan
1`, and only Gi0/1 marked `ip dhcp snooping trust`. Server messages (offers,
acks) arriving on untrusted ports are dropped, so only R1's offers reach the
PCs. `no ip dhcp snooping information option` stops the switch adding option
82, which R1 (not a relay) would otherwise refuse.

Check in Packet Tracer:
  - PC1 to PC3 Desktop > IP Configuration: DHCP gives 192.168.1.11 and up
    with gateway 192.168.1.1 (R1), never 192.168.1.254
  - SW1 `show ip dhcp snooping`: enabled on VLAN 1, Gi0/1 trusted
  - SW1 `show ip dhcp snooping binding`: one binding per PC
  - ROGUE `show ip dhcp binding`: empty
  - PC1 `ping 8.8.8.8` works through R1
"""

import pktlib

net = pktlib.new()
isp = net.router("ISP", "2911", at=(800, 60))
outside = net.server("INTERNET", at=(1050, 60), ip="8.8.8.8/24", gateway="8.8.8.1")
r1 = net.router("R1", "2911", at=(500, 60))
sw = net.switch("SW1", "2960-24TT", at=(500, 220))
rogue = net.router("ROGUE", "1841", at=(850, 220))

isp["g0/0"].connect(outside["fa0"])
isp["g0/0"].address = "8.8.8.1/24"
isp["g0/1"].connect(r1["g0/1"])
isp["g0/1"].address = "203.0.113.1/30"
r1["g0/1"].address = "203.0.113.2/30"
isp.config("ip route 192.168.1.0 255.255.255.0 203.0.113.2")

r1["g0/0"].connect(sw["g0/1"])
r1["g0/0"].address = "192.168.1.1/24"
r1.config("""
ip route 0.0.0.0 0.0.0.0 203.0.113.1
ip dhcp excluded-address 192.168.1.1 192.168.1.10
ip dhcp pool LAN
 network 192.168.1.0 255.255.255.0
 default-router 192.168.1.1
 dns-server 8.8.8.8
""")

# the rogue: on an ordinary access port, with a pool that points PCs at itself
rogue["fa0/0"].connect(sw["fa0/24"])
rogue["fa0/0"].address = "192.168.1.254/24"
rogue.config("""
ip dhcp excluded-address 192.168.1.1 192.168.1.99
ip dhcp excluded-address 192.168.1.200 192.168.1.254
ip dhcp pool EVIL
 network 192.168.1.0 255.255.255.0
 default-router 192.168.1.254
 dns-server 192.168.1.254
""")

sw.config("""
ip dhcp snooping
ip dhcp snooping vlan 1
no ip dhcp snooping information option
interface g0/1
 ip dhcp snooping trust
""")
for i in range(1, 4):
    pc = net.pc(f"PC{i}", at=(300 + 200 * (i - 1), 400))
    pc.use_dhcp()
    sw[f"fa0/{i}"].connect(pc["fa0"])
    sw.config(f"interface fa0/{i}\n switchport mode access\n spanning-tree portfast")

net.around(rogue, shape="ellipse", outline="red", label="ROGUE DHCP: untrusted port, offers dropped", pad=30)
net.note("Gi0/1: ip dhcp snooping trust", at=(560, 140))
net.around(isp, outside, shape="rectangle", outline="grey", label="INTERNET", pad=30)

net.ping("PC1", "INTERNET", scenario="DHCP client out through the real gateway")
net.ping("PC3", "INTERNET", scenario="DHCP client out through the real gateway")
net.ping("PC2", "R1", ip="192.168.1.1", scenario="DHCP client to its real gateway")

net.save("dhcp_snooping.pkt")
print(f"dhcp_snooping.pkt: {len(net.devices)} devices, {len(net.links)} links")
