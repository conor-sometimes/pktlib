"""Stress: rapid-PVST with the root split per VLAN, 24 VLANs, pruned trunks, native VLAN.

Two 3560 distribution switches (DIST1, DIST2) and six 2960 access switches, every
access switch trunked to both, so each VLAN has a loop to break.
  VLANs     100-111 (created with one `vlan 100-111` range) and 200-211 (a comma list)
  roots     DIST1: `spanning-tree vlan 100-111 root primary`, `200-211 root secondary`
            DIST2: the reverse, written as priority numbers (4096 and 28672)
  trunks    native VLAN 999 everywhere, allowed lists pruned per access switch
            (ACC1-3 carry 100-111, ACC4-6 carry 200-211, the DIST1-DIST2 link carries all),
            plus one `switchport trunk allowed vlan add` line
  edge      portfast + bpduguard on every host port, root guard on DIST downlinks,
            loop guard on the access uplinks
  hosts     two PCs per access switch, 12 in all, in VLAN 100+n and 200+n

Check in Packet Tracer:
  DIST1# show spanning-tree vlan 105    -> "This bridge is the root", mode rstp
  DIST2# show spanning-tree vlan 205    -> "This bridge is the root"
  ACC1#  show spanning-tree vlan 100    -> Gi0/2 (to DIST2) Altn BLK
  ACC4#  show spanning-tree vlan 200    -> Gi0/1 (to DIST1) Altn BLK
  ACC1#  show interfaces trunk          -> native 999, allowed 100-111,999
  PC-A1-1 ping PC-A3-1 (same VLAN 100, different access switches) -> success
  DIST1# show vlan brief                -> 100-111 and 200-211 named, plus 999
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw02_rpvst_roots.pkt"
LOW = list(range(100, 112))
HIGH = list(range(200, 212))
NATIVE = 999
problems: list[str] = []

net = pktlib.new()
dists = [net.multilayer(f"DIST{i}", "3560-24PS", at=(400 + 600 * (i - 1), 120)) for i in (1, 2)]
for i, d in enumerate(dists):
    other = "secondary" if i == 0 else "primary"
    first = "primary" if i == 0 else "secondary"
    d.config(f"""
spanning-tree mode rapid-pvst
vlan 100-111
 name LOW
vlan {",".join(map(str, HIGH))}
 name HIGH
vlan {NATIVE}
 name NATIVE
""")
    if i == 0:
        d.config(f"spanning-tree vlan 100-111 root {first}\nspanning-tree vlan 200-211 root {other}")
    else:
        d.config("spanning-tree vlan 200-211 priority 4096\nspanning-tree vlan 100-111 priority 28672")
    # DIST1 <-> DIST2 on g0/1, carries everything
    d.config(f"""
interface g0/1
 switchport trunk encapsulation dot1q
 switchport mode trunk
 switchport trunk native vlan {NATIVE}
 switchport trunk allowed vlan 100-111,200-211,{NATIVE}
""")
dists[0]["g0/1"].connect(dists[1]["g0/1"])

# The VLAN range lines must have gone into the VLAN database
for d in dists:
    missing = [v for v in LOW + HIGH + [NATIVE] if v not in d.vlans]
    if missing:
        problems.append(f"{d.name} VLAN database is missing {missing}")
    names = {d.vlans.get(100), d.vlans.get(205)}
    if names != {"LOW", "HIGH"}:
        problems.append(
            f"{d.name} VLAN names after range/list `name`: 100={d.vlans.get(100)!r} 205={d.vlans.get(205)!r}"
        )

for a in range(6):
    acc = net.switch(f"ACC{a + 1}", "2960-24TT", at=(100 + 220 * a, 330))
    carry = LOW if a < 3 else HIGH
    allowed = f"{carry[0]}-{carry[-1]},{NATIVE}"
    acc.config("spanning-tree mode rapid-pvst")
    # uplinks: gig0/1 to DIST1, gig0/2 to DIST2
    for u, d in enumerate(dists, 1):
        acc.config(f"""
interface g0/{u}
 switchport mode trunk
 switchport trunk native vlan {NATIVE}
 switchport trunk allowed vlan {allowed}
 spanning-tree guard loop
""")
        dport = f"fa0/{a + 1}"
        d.config(f"""
interface {dport}
 switchport trunk encapsulation dot1q
 switchport mode trunk
 switchport trunk native vlan {NATIVE}
 switchport trunk allowed vlan {allowed}
 spanning-tree guard root
""")
        acc[f"g0/{u}"].connect(d[dport])
    if a == 0:
        # an `add` on top of the list, as people do when a VLAN is added later
        acc.config("interface g0/1\n switchport trunk allowed vlan add 211")
    for h in range(2):
        vid = carry[h * 5]
        pc = net.pc(
            f"PC-A{a + 1}-{h + 1}",
            at=(60 + 220 * a + 90 * h, 480),
            ip=f"10.{vid % 256}.0.{10 + a}/24",
            gateway=f"10.{vid % 256}.0.1",
        )
        acc[f"fa0/{h + 1}"].connect(pc["fa0"])
        acc.config(f"""
interface fa0/{h + 1}
 switchport mode access
 switchport access vlan {vid}
 spanning-tree portfast
 spanning-tree bpduguard enable
""")
    # pruned VLANs still need to exist on the access switch for its own PCs
    for v in carry:
        acc.add_vlan(v)
    acc.add_vlan(NATIVE, "NATIVE")

# gateways: DIST1 owns 100-111, DIST2 owns 200-211, so PCs have someone to answer
for d, vids in ((dists[0], LOW), (dists[1], HIGH)):
    cfg = ["ip routing"]
    for v in vids:
        cfg += [f"interface vlan {v}", f" ip address 10.{v % 256}.0.1 255.255.255.0", " no shutdown"]
    d.config(cfg)

net.around(*dists, label="per-VLAN roots", outline="blue", pad=40)
net.save(OUT)
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
