"""Stress: five EtherChannels on one 3650, every flavour at once.

CORE1 (3650) holds:
  Po1  LACP active/active, layer 2 trunk to CORE2, allowed VLANs 10,20,30,99, native 99
  Po2  PAgP desirable/auto, layer 2 trunk to DIST (a 3560, on its two gig ports)
  Po3  LACP active/passive, LAYER 3 (no switchport), 10.99.0.0/30 to CORE2, OSPF over it
  Po4  static (mode on), trunk to ACC1 (a 2960, on its two gig ports)
  Po5  a second layer 3 LACP bundle to CORE2 on g1/1/1-2 (the uplink ports),
       10.99.0.4/30

Also: a PC per VLAN on DIST and ACC1, SVIs on CORE1 only (it routes), OSPF across
both layer 3 channels so CORE2's loopback is reachable twice.

Check in Packet Tracer:
  CORE1# show etherchannel summary   -> Po1(SU) LACP, Po2(SU) PAgP, Po3(RU) LACP,
                                         Po4(SU) -, Po5(RU) LACP, all members (P)
  CORE1# show ip ospf neighbor       -> CORE2 twice, once on Po3 and once on Po5
  CORE1# show interfaces trunk       -> Po1 native 99, allowed 10,20,30,99
  PC-V10-DIST ping 10.30.0.11 (PC-V30-ACC1)  -> routed by CORE1's SVIs
  CORE1# ping 2.2.2.2                 -> CORE2's loopback over the layer 3 channels
  Also look at the order of the Port-channel blocks in CORE1's show run (Po1..Po5).
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw01_many_channels.pkt"
VLANS = {10: "USERS", 20: "SERVERS", 30: "PRINT", 99: "NATIVE"}
problems: list[str] = []

net = pktlib.new()
core1 = net.multilayer("CORE1", "3650-24PS", at=(400, 150))
core2 = net.multilayer("CORE2", "3650-24PS", at=(900, 150))
dist = net.multilayer("DIST", "3560-24PS", at=(250, 400))
acc1 = net.switch("ACC1", "2960-24TT", at=(650, 400))

for core in (core1, core2):
    for vid, name in VLANS.items():
        core.add_vlan(vid, name)

# Po1: LACP layer 2 trunk CORE1 <-> CORE2 on g1/0/23-24, with an allowed list and native VLAN
po1 = """
interface port-channel 1
 switchport mode trunk
 switchport trunk native vlan 99
 switchport trunk allowed vlan 10,20,30,99
interface range g1/0/23 - 24
 switchport mode trunk
 switchport trunk native vlan 99
 switchport trunk allowed vlan 10,20,30,99
 channel-group 1 mode active
"""
core1.config(po1)
core2.config(po1)
for p in ("g1/0/23", "g1/0/24"):
    core1[p].connect(core2[p])

# Po3: layer 3 LACP CORE1 (active) <-> CORE2 (passive) on g1/0/19-20
for core, me, mode in ((core1, 1, "active"), (core2, 2, "passive")):
    core.config(f"""
interface port-channel 3
 no switchport
 ip address 10.99.0.{me} 255.255.255.252
interface range g1/0/19 - 20
 no switchport
 no ip address
 channel-group 3 mode {mode}
""")
for p in ("g1/0/19", "g1/0/20"):
    core1[p].connect(core2[p])

# Po5: second layer 3 LACP channel on the 1/1/x uplinks
for core, me in ((core1, 5), (core2, 6)):
    core.config(f"""
interface port-channel 5
 no switchport
 ip address 10.99.0.{me} 255.255.255.252
interface range g1/1/1 - 2
 no switchport
 no ip address
 channel-group 5 mode active
""")
for p in ("g1/1/1", "g1/1/2"):
    core1[p].connect(core2[p])

# Po2: PAgP to DIST. CORE1 desirable on g1/0/1-2, DIST auto on its g0/1-2 (3560 needs encapsulation)
core1.config("""
interface port-channel 2
 switchport mode trunk
interface range g1/0/1 - 2
 switchport mode trunk
 channel-group 2 mode desirable
""")
dist.config("""
interface port-channel 2
 switchport trunk encapsulation dot1q
 switchport mode trunk
interface range g0/1 - 2
 switchport trunk encapsulation dot1q
 switchport mode trunk
 channel-group 2 mode auto
""")
core1["g1/0/1"].connect(dist["g0/1"])
core1["g1/0/2"].connect(dist["g0/2"])

# Po4: static channel to ACC1
core1.config("""
interface port-channel 4
 switchport mode trunk
interface range g1/0/3 - 4
 switchport mode trunk
 channel-group 4 mode on
""")
acc1.config("""
interface port-channel 1
 switchport mode trunk
interface range g0/1 - 2
 switchport mode trunk
 channel-group 1 mode on
""")
core1["g1/0/3"].connect(acc1["g0/1"])
core1["g1/0/4"].connect(acc1["g0/2"])

# CORE1 routes: SVIs, OSPF over both layer 3 channels
cfg = ["ip routing", "spanning-tree mode rapid-pvst", "spanning-tree vlan 10,20,30,99 priority 4096"]
for vid in (10, 20, 30):
    cfg += [f"interface vlan {vid}", f" ip address 10.{vid}.0.1 255.255.255.0", " no shutdown"]
cfg += [
    "interface loopback 0",
    " ip address 1.1.1.1 255.255.255.255",
    "router ospf 1",
    " router-id 1.1.1.1",
    " network 10.99.0.0 0.0.0.7 area 0",
    " network 1.1.1.1 0.0.0.0 area 0",
]
cfg += [f" network 10.{v}.0.0 0.0.0.255 area 0" for v in (10, 20, 30)]
core1.config(cfg)
core2.config("""
ip routing
spanning-tree mode rapid-pvst
spanning-tree vlan 10,20,30,99 priority 8192
interface loopback 0
 ip address 2.2.2.2 255.255.255.255
router ospf 1
 router-id 2.2.2.2
 network 10.99.0.0 0.0.0.7 area 0
 network 2.2.2.2 0.0.0.0 area 0
""")
dist.config("spanning-tree mode rapid-pvst")
acc1.config("spanning-tree mode rapid-pvst")

# hosts: one per VLAN on DIST and ACC1
for sw, tag, x0 in ((dist, "DIST", 120), (acc1, "ACC1", 520)):
    for i, vid in enumerate((10, 20, 30)):
        host = 10 if sw is dist else 11
        pc = net.pc(f"PC-V{vid}-{tag}", at=(x0 + 110 * i, 560), ip=f"10.{vid}.0.{host}/24", gateway=f"10.{vid}.0.1")
        sw[f"fa0/{i + 1}"].connect(pc["fa0"])
        sw.config(
            f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {vid}\n spanning-tree portfast"
        )

net.around(core1, core2, label="Po1 L2 LACP, Po3 + Po5 L3 LACP", outline="blue", pad=40)
net.save(OUT)

# What the library wrote: Port-channel block order on CORE1
order = [l for l in core1.running_config if l.startswith("interface Port-channel")]
print("CORE1 Port-channel order in running config:", order)
if order != sorted(order, key=lambda l: int(l.rsplit("l", 1)[1])):
    problems.append(f"CORE1 Port-channel blocks out of IOS order: {order}")
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
