"""EtherChannel two ways: an LACP bundle and a PAgP bundle, both trunking to a multilayer switch.

    uv run python examples/ccna/etherchannel.py        # writes etherchannel.pkt

DSW (a 3560) has two access switches, each on a pair of cables bundled into
one logical link, so spanning tree sees one port and both cables carry
traffic:

  Po1  DSW Gi0/1-2 to ACC1 Gi0/1-2, LACP (the open standard):
       DSW `mode active`, ACC1 `mode passive`
  Po2  DSW Fa0/23-24 to ACC2 Fa0/23-24, PAgP (Cisco's own):
       DSW `mode desirable`, ACC2 `mode auto`

Each bundle is a trunk; the trunk settings go on the Port-channel interface
and on every member port alike. DSW routes between VLAN 10 and VLAN 20 with
SVIs. Two passive (or two auto) ends would never form a channel: one end has
to start the negotiation.

Check in Packet Tracer:
  - DSW `show etherchannel summary`: Po1(SU) LACP with Gi0/1(P) Gi0/2(P),
    Po2(SU) PAgP with Fa0/23(P) Fa0/24(P)
  - ACC1 `show etherchannel summary`: Po1(SU) LACP
  - DSW `show interfaces trunk`: Po1 and Po2 trunking (not the member ports)
  - DSW `show spanning-tree vlan 10`: Po1 and Po2 listed as single ports
  - PC-A1-10 `ping 10.0.20.22` (PC-A2-20): over both channels, routed by DSW
"""

import pktlib

net = pktlib.new()
dsw = net.multilayer("DSW", "3560-24PS", at=(500, 120))
acc1 = net.switch("ACC1", "2960-24TT", at=(250, 330))
acc2 = net.switch("ACC2", "2960-24TT", at=(750, 330))

cfg = ["ip routing"]
for vid in (10, 20):
    dsw.add_vlan(vid, f"VLAN{vid}")
    cfg += [f"interface vlan {vid}", f" ip address 10.0.{vid}.1 255.255.255.0", " no shutdown"]
dsw.config(cfg)

TRUNK_3560 = " switchport trunk encapsulation dot1q\n switchport mode trunk"
# Po2 is set up before Po1: pktlib puts each new Port-channel ahead of the
# others, and this way they come out in IOS order (Po1, then Po2).
# Po2: PAgP to ACC2 on two FastEthernet ports
dsw.config(f"""
interface port-channel 2
{TRUNK_3560}
interface range fa0/23 - 24
{TRUNK_3560}
 channel-group 2 mode desirable
""")
acc2.config("""
interface port-channel 2
 switchport mode trunk
interface range fa0/23 - 24
 switchport mode trunk
 channel-group 2 mode auto
""")
# Po1: LACP to ACC1 on the gigabit ports
dsw.config(f"""
interface port-channel 1
{TRUNK_3560}
interface range g0/1 - 2
{TRUNK_3560}
 channel-group 1 mode active
""")
acc1.config("""
interface port-channel 1
 switchport mode trunk
interface range g0/1 - 2
 switchport mode trunk
 channel-group 1 mode passive
""")
for p in ("g0/1", "g0/2"):
    dsw[p].connect(acc1[p])
for p in ("fa0/23", "fa0/24"):
    dsw[p].connect(acc2[p])

for n, acc in ((1, acc1), (2, acc2)):
    for port, vid in enumerate((10, 20), 1):
        acc.add_vlan(vid, f"VLAN{vid}")
        pc = net.pc(
            f"PC-A{n}-{vid}",
            at=(acc.xy[0] - 70 + 140 * (port - 1), 480),
            ip=f"10.0.{vid}.{10 * n + port}/24",
            gateway=f"10.0.{vid}.1",
        )
        acc[f"fa0/{port}"].connect(pc["fa0"])
        acc.config(
            f"interface fa0/{port}\n switchport mode access\n switchport access vlan {vid}\n spanning-tree portfast"
        )

net.note("Po1: LACP\nactive / passive", at=(250, 200))
net.note("Po2: PAgP\ndesirable / auto", at=(680, 200))
net.around(dsw, shape="ellipse", outline="blue", label="SVIs 10 and 20", pad=30)

net.ping("PC-A1-10", "PC-A2-20", scenario="Across both EtherChannels")
net.ping("PC-A1-20", "PC-A2-20", scenario="Same VLAN across both EtherChannels")
net.ping("PC-A2-10", "DSW", ip="10.0.10.1", scenario="Over the PAgP channel to the gateway")

net.save("etherchannel.pkt")
print(f"etherchannel.pkt: {len(net.devices)} devices, {len(net.links)} links")
