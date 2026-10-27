"""Stress: HSRP version 2 on 21 SVIs, split active per VLAN, DHCP relay to a router.

Two 3650 cores with an LACP trunk (Po1) between them. 20 user VLANs (10-29) and a
services VLAN (900). Every SVI has `standby version 2`, group = VLAN number, a
virtual .1, CORE1 active on odd VLANs and CORE2 on even (priority 150 vs 100,
preempt), and the rapid-PVST root follows the HSRP active. Every user SVI has
`ip helper-address 10.9.0.10`. DHCP-SRV (a 2911 in VLAN 900) holds 20 pools.
Two 2960 access switches, each dual-homed, 20 DHCP PCs on each (one per VLAN on
each switch), so 40 DHCP clients in all.

Check in Packet Tracer:
  CORE1# show standby brief          -> 21 groups; Active on 11,13,..,29, Standby on even
  CORE2# show standby brief          -> the opposite
  CORE1# show etherchannel summary   -> Po1(SU) LACP
  PC-A1-V17 (any PC) Desktop > IP Configuration > DHCP -> 10.1.17.x, gateway 10.1.17.1
  DHCP-SRV# show ip dhcp binding     -> up to 40 bindings across 20 pools
  PC-A1-V10 ping PC-A2-V29's address -> routed between VLANs through the HSRP gateways
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw03_hsrp_relay.pkt"
USER = list(range(10, 30))
SVC = 900
SRV = "10.9.0.10"

net = pktlib.new()
cores = [net.multilayer(f"CORE{i}", "3650-24PS", at=(450 + 500 * (i - 1), 120)) for i in (1, 2)]
for c, core in enumerate(cores, 1):
    odd_pri, even_pri = (4096, 8192) if c == 1 else (8192, 4096)
    odd = ",".join(str(v) for v in USER if v % 2)
    even = ",".join(str(v) for v in USER if not v % 2) + f",{SVC}"
    cfg = [
        "ip routing",
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan {odd} priority {odd_pri}",
        f"spanning-tree vlan {even} priority {even_pri}",
        "interface port-channel 1",
        " switchport mode trunk",
        "interface range g1/0/23 - 24",
        " switchport mode trunk",
        " channel-group 1 mode active",
        "interface range g1/0/1 - 2",
        " switchport mode trunk",
        f"vlan {SVC}",
        " name SERVICES",
    ]
    for v in USER + [SVC]:
        net_ = f"10.1.{v}" if v != SVC else "10.9.0"
        mine_active = (v % 2 == 1) == (c == 1)
        cfg += [
            f"vlan {v}",
            f" name USER{v}" if v != SVC else " name SERVICES",
            f"interface vlan {v}",
            f" ip address {net_}.{1 + c} 255.255.255.0",
            " standby version 2",
            f" standby {v} ip {net_}.1",
            f" standby {v} priority {150 if mine_active else 100}",
            f" standby {v} preempt",
        ]
        if v != SVC:
            cfg += [f" ip helper-address {SRV}"]
        cfg += [" no shutdown"]
    core.config(cfg)
for p in ("g1/0/23", "g1/0/24"):
    cores[0][p].connect(cores[1][p])

# DHCP server: a router in the services VLAN
srv = net.router("DHCP-SRV", "2911", at=(1300, 300))
srv["g0/0"].address = f"{SRV}/24"
pools = ["ip route 0.0.0.0 0.0.0.0 10.9.0.1"]
for v in USER:
    pools += [
        f"ip dhcp excluded-address 10.1.{v}.1 10.1.{v}.9",
        f"ip dhcp pool USER{v}",
        f" network 10.1.{v}.0 255.255.255.0",
        f" default-router 10.1.{v}.1",
        " dns-server 10.9.0.53",
    ]
srv.config(pools)

for a in range(2):
    acc = net.switch(f"ACC{a + 1}", "2960-24TT", at=(350 + 600 * a, 300))
    acc.config("spanning-tree mode rapid-pvst")
    for u, core in enumerate(cores, 1):
        acc.config(f"interface g0/{u}\n switchport mode trunk")
        acc[f"g0/{u}"].connect(core[f"g1/0/{a + 1}"])
    for i, v in enumerate(USER):
        x = 40 + 600 * a + (i % 10) * 60
        y = 450 + (i // 10) * 110
        pc = net.pc(f"PC-A{a + 1}-V{v}", at=(x, y))
        pc.use_dhcp()
        acc[f"fa0/{i + 1}"].connect(pc["fa0"])
        acc.config(
            f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {v}\n spanning-tree portfast"
        )
    if a == 1:
        acc["fa0/24"].connect(srv["g0/0"])
        acc.config(f"interface fa0/24\n switchport mode access\n switchport access vlan {SVC}")

net.around(*cores, label="HSRPv2 x21, relay to 10.9.0.10", outline="blue", pad=40)
net.save(OUT)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
