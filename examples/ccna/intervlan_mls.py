"""Inter-VLAN routing on a multilayer switch: SVIs, `ip routing` and a routed uplink port.

    uv run python examples/ccna/intervlan_mls.py        # writes intervlan_mls.pkt

DSW, a 3560, is the gateway for three VLANs (10 STAFF, 20 STUDENTS,
30 PRINTERS). Instead of a router on a stick, the switch routes itself:

  - `ip routing` turns routing on (a 3560 only switches without it)
  - one SVI per VLAN (`interface vlan 10`, ...) holds that VLAN's gateway
  - trunks to the two access switches, with `switchport trunk encapsulation
    dot1q` first (the 3560 also speaks ISL, so it has to be told)
  - Gi0/2 is a routed port (`no switchport`) to EDGE, with a default route
    pointing at it; EDGE has a static route back for 10.10.0.0/16

Check in Packet Tracer:
  - DSW `show ip route`: C for Vlan10, Vlan20, Vlan30 and Gi0/2, plus
    S* 0.0.0.0/0 via 10.0.0.2
  - DSW `show ip interface brief`: Vlan10, Vlan20, Vlan30 up/up
  - DSW `show interfaces trunk`: Gi0/1 and Fa0/24 trunking, 802.1q
  - STAFF1 `tracert 10.10.20.11` (STUDENT1): one hop, 10.10.10.1 (DSW)
  - STUDENT2 `ping 203.0.113.10` (the server behind EDGE)
"""

import pktlib

VLANS = {10: "STAFF", 20: "STUDENTS", 30: "PRINTERS"}

net = pktlib.new()
edge = net.router("EDGE", "2911", at=(500, 40))
server = net.server("SERVER", at=(800, 40), ip="203.0.113.10/24", gateway="203.0.113.1")
dsw = net.multilayer("DSW", "3560-24PS", at=(500, 200))
acc = [net.switch(f"ACC{n}", at=(250 + 500 * (n - 1), 360)) for n in (1, 2)]

edge["g0/1"].connect(server["fa0"])
edge["g0/1"].address = "203.0.113.1/24"
edge["g0/0"].connect(dsw["g0/2"])
edge["g0/0"].address = "10.0.0.2/30"
edge.config("ip route 10.10.0.0 255.255.0.0 10.0.0.1")

cfg = [
    "ip routing",
    "interface g0/2",
    " no switchport",
    " ip address 10.0.0.1 255.255.255.252",
    " no shutdown",
    "ip route 0.0.0.0 0.0.0.0 10.0.0.2",
]
for vid, name in VLANS.items():
    dsw.add_vlan(vid, name)
    cfg += [f"interface vlan {vid}", f" ip address 10.10.{vid}.1 255.255.255.0", " no shutdown"]
for port in ("g0/1", "fa0/24"):
    cfg += [f"interface {port}", " switchport trunk encapsulation dot1q", " switchport mode trunk"]
dsw.config(cfg)
dsw["g0/1"].connect(acc[0]["g0/1"])
dsw["fa0/24"].connect(acc[1]["g0/1"])

# each access switch: a staff PC, a student PC, a printer
KIND = {10: ("STAFF", net.pc), 20: ("STUDENT", net.pc), 30: ("PRINTER", net.printer)}
for n, sw in enumerate(acc, 1):
    for vid, name in VLANS.items():
        sw.add_vlan(vid, name)
    sw.config("interface g0/1\n switchport mode trunk")
    x = sw.xy[0]
    for port, (vid, (who, make)) in enumerate(KIND.items(), 1):
        host = make(
            f"{who}{n}", at=(x - 130 + 130 * (port - 1), 500), ip=f"10.10.{vid}.1{n}/24", gateway=f"10.10.{vid}.1"
        )
        sw[f"fa0/{port}"].connect(host["fa0"])
        sw.config(
            f"interface fa0/{port}\n switchport mode access\n switchport access vlan {vid}\n spanning-tree portfast"
        )

net.around(dsw, shape="ellipse", outline="blue", label="ip routing: SVIs 10, 20, 30", pad=40)
net.around(edge, server, shape="rectangle", outline="grey", label="routed port Gi0/2 to EDGE", pad=30)
net.note(
    "VLAN 10 STAFF  10.10.10.0/24\nVLAN 20 STUDENTS  10.10.20.0/24\nVLAN 30 PRINTERS  10.10.30.0/24", at=(420, 580)
)

net.ping("STAFF1", "STUDENT2", scenario="Between VLANs through the SVIs")
net.ping("STUDENT1", "PRINTER2", scenario="Between VLANs through the SVIs")
net.ping("STAFF2", "SERVER", scenario="Out the routed port to EDGE")

net.save("intervlan_mls.pkt")
print(f"intervlan_mls.pkt: {len(net.devices)} devices, {len(net.links)} links")
