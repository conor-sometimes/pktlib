"""Spanning tree on a switch triangle: a chosen root bridge per VLAN, PortFast and BPDU guard.

    uv run python examples/ccna/stp.py        # writes stp.pkt

Two distribution switches (DSW1, DSW2, 3560s) and an access switch (ACC, a
2960) are cabled in a triangle, so every VLAN has a loop for spanning tree to
break. All three run rapid PVST+ (`spanning-tree mode rapid-pvst`), one tree
per VLAN, and the root is chosen by hand with bridge priorities:

  VLAN 10  DSW1 priority 4096 (root), DSW2 8192 (backup root)
  VLAN 20  DSW2 priority 4096 (root), DSW1 8192 (backup root)

So the two VLANs block different uplinks on ACC and both uplinks carry
traffic. ACC's host ports have `spanning-tree portfast` (they go straight to
forwarding, no listening and learning) and `spanning-tree bpduguard enable`
(the port shuts if a switch is plugged in). DSW1 and DSW2 also route between
the VLANs with SVIs, each the gateway for the VLAN it is root for.

Check in Packet Tracer:
  - DSW1 `show spanning-tree vlan 10`: "This bridge is the root", priority 4106
  - DSW2 `show spanning-tree vlan 20`: "This bridge is the root"
  - ACC `show spanning-tree vlan 10`: Gi0/1 Root FWD, Gi0/2 Altn BLK;
    `show spanning-tree vlan 20`: the other way round
  - ACC `show spanning-tree interface fa0/1 detail`: portfast and bpdu guard on
  - PC10-1 `ping 10.0.20.11` (PC20-1): routed by DSW1 across the tree
"""

import pktlib

net = pktlib.new()
dsw1 = net.multilayer("DSW1", "3560-24PS", at=(250, 120))
dsw2 = net.multilayer("DSW2", "3560-24PS", at=(750, 120))
acc = net.switch("ACC", "2960-24TT", at=(500, 380))

ROOT = {dsw1: 10, dsw2: 20}  # the VLAN each one is root for
for me, other in ((dsw1, dsw2), (dsw2, dsw1)):
    mine, theirs = ROOT[me], ROOT[other]
    cfg = [
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan {mine} priority 4096",
        f"spanning-tree vlan {theirs} priority 8192",
        "ip routing",
    ]
    for vid in (10, 20):
        me.add_vlan(vid, "USERS" if vid == 10 else "STAFF")
        host = 1 if vid == mine else 2  # .1 on the switch that is root for the VLAN
        cfg += [f"interface vlan {vid}", f" ip address 10.0.{vid}.{host} 255.255.255.0", " no shutdown"]
    for port in ("g0/1", "g0/2"):
        cfg += [f"interface {port}", " switchport trunk encapsulation dot1q", " switchport mode trunk"]
    me.config(cfg)

dsw1["g0/1"].connect(dsw2["g0/1"])
dsw1["g0/2"].connect(acc["g0/1"])
dsw2["g0/2"].connect(acc["g0/2"])

acc.add_vlan(10, "USERS")
acc.add_vlan(20, "STAFF")
acc.config("spanning-tree mode rapid-pvst\ninterface range g0/1 - 2\n switchport mode trunk")
for port, vid in enumerate((10, 10, 20, 20), 1):
    k = 1 if port % 2 else 2
    pc = net.pc(f"PC{vid}-{k}", at=(260 + 160 * (port - 1), 540), ip=f"10.0.{vid}.1{k}/24", gateway=f"10.0.{vid}.1")
    acc[f"fa0/{port}"].connect(pc["fa0"])
    acc.config(f"""
interface fa0/{port}
 switchport mode access
 switchport access vlan {vid}
 spanning-tree portfast
 spanning-tree bpduguard enable
""")

net.note("VLAN 10 root\npriority 4096", at=(140, 30))
net.note("VLAN 20 root\npriority 4096", at=(760, 30))
net.note("Gi0/2 blocks VLAN 10\nGi0/1 blocks VLAN 20", at=(600, 330))
net.around(dsw1, dsw2, acc, shape="ellipse", outline="blue", label="rapid PVST+ triangle", pad=40)
net.around(
    "PC10-1", "PC10-2", "PC20-1", "PC20-2", shape="rectangle", outline="green", label="PortFast + BPDU guard", pad=20
)

net.ping("PC10-1", "PC10-2", scenario="Same VLAN on the access switch")
net.ping("PC10-1", "PC20-1", scenario="VLAN 10 to VLAN 20 across the tree")
net.ping("PC20-2", "DSW2", ip="10.0.20.1", scenario="VLAN 20 to its root and gateway")

net.save("stp.pkt")
print(f"stp.pkt: {len(net.devices)} devices, {len(net.links)} links")
