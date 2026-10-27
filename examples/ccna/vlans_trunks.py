"""VLANs on two switches joined by an 802.1Q trunk, with a native VLAN and a pruned allowed list.

    uv run python examples/ccna/vlans_trunks.py        # writes vlans_trunks.pkt

SW1 and SW2 each have one PC in each of three VLANs: 10 SALES, 20 ENGINEERING
and 30 LAB. The trunk between their Gi0/1 ports carries VLANs 10, 20 and 99
only: VLAN 30 is left off the allowed list on purpose, so the two LAB PCs
can't reach each other even though they share a subnet. R1 hangs off SW1 on a
second trunk and routes between the VLANs (a router on a stick), so each PC
has a gateway. What the config shows:

  - VLANs created and named, including 99 MANAGEMENT and 999 PARKING
  - access ports: `switchport mode access`, `switchport access vlan`
  - trunks: `switchport mode trunk`, `switchport trunk native vlan 99`
    (untagged frames go to VLAN 99, not VLAN 1) on both ends of every trunk,
    `switchport trunk allowed vlan`; R1's native VLAN is
    `encapsulation dot1Q 99 native`
  - a management SVI (interface vlan 99) and `ip default-gateway` per switch
  - every unused port parked in VLAN 999 and shut down

Check in Packet Tracer:
  - SW1 `show vlan brief`: VLANs 10, 20, 30 on Fa0/1-3, the rest in 999
  - SW1 `show interfaces trunk`: Gi0/1 native 99, allowed 10,20,99;
    Gi0/2 (to R1) allowed 10,20,30,99
  - SW2 `ping 192.168.99.1` (R1, over the native VLAN) and
    `ping 192.168.99.11` (SW1's management SVI)
  - SALES1 `ping 192.168.10.12` (SALES2): same VLAN across the trunk
  - LAB2 `ping 192.168.30.11` (LAB1) fails: VLAN 30 isn't allowed on the
    SW1 to SW2 trunk
"""

import pktlib

VLANS = {10: "SALES", 20: "ENGINEERING", 30: "LAB", 99: "MANAGEMENT", 999: "PARKING"}
USERS = {10: "SALES", 20: "ENG", 30: "LAB"}

net = pktlib.new()
r1 = net.router("R1", "2911", at=(300, 60))
switches = [net.switch(f"SW{n}", at=(300 + 450 * (n - 1), 220)) for n in (1, 2)]
sw1, sw2 = switches
sw1["g0/1"].connect(sw2["g0/1"])
sw1["g0/2"].connect(r1["g0/0"])

for n, sw in enumerate(switches, 1):
    for vid, name in VLANS.items():
        sw.add_vlan(vid, name)
    sw.config(f"""
interface g0/1
 switchport mode trunk
 switchport trunk native vlan 99
 switchport trunk allowed vlan 10,20,99
interface range fa0/4 - 24
 switchport mode access
 switchport access vlan 999
 shutdown
interface vlan 1
 shutdown
interface vlan 99
 ip address 192.168.99.1{n} 255.255.255.0
 no shutdown
ip default-gateway 192.168.99.1
""")
    x = sw.xy[0]
    for port, (vid, who) in enumerate(USERS.items(), 1):
        pc = net.pc(
            f"{who}{n}", at=(x - 130 + 130 * (port - 1), 380), ip=f"192.168.{vid}.1{n}/24", gateway=f"192.168.{vid}.1"
        )
        sw[f"fa0/{port}"].connect(pc["fa0"])
        sw.config(f"interface fa0/{port}\n switchport mode access\n switchport access vlan {vid}")

# SW1's second trunk, to R1: every VLAN, VLAN 30 included
sw1.config("""
interface g0/2
 switchport mode trunk
 switchport trunk native vlan 99
 switchport trunk allowed vlan 10,20,30,99
""")
sw2.config("interface g0/2\n switchport mode access\n switchport access vlan 999\n shutdown")
r1_cfg = ["interface g0/0", " no shutdown"]
for vid in (10, 20, 30, 99):
    native = " native" if vid == 99 else ""
    r1_cfg += [
        f"interface g0/0.{vid}",
        f" encapsulation dot1Q {vid}{native}",
        f" ip address 192.168.{vid}.1 255.255.255.0",
    ]
r1.config(r1_cfg)

net.around(sw1, sw2, shape="rectangle", outline="blue", label="trunk Gi0/1: native 99, allowed 10,20,99", pad=40)
net.note("VLAN 10 SALES, 20 ENGINEERING, 30 LAB\n(30 is pruned from the SW1 to SW2 trunk)", at=(420, 460))
net.note("router on a stick:\nG0/0.10 .20 .30 .99", at=(420, 50))

net.ping("SALES1", "SALES2", scenario="Same VLAN across the trunk")
net.ping("ENG2", "SALES1", scenario="Between VLANs through R1")
net.ping("LAB2", "LAB1", scenario="VLAN 30 not on the trunk: should FAIL")

net.save("vlans_trunks.pkt")
print(f"vlans_trunks.pkt: {len(net.devices)} devices, {len(net.links)} links")
