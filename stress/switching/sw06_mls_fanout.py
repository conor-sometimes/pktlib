"""Stress: one 3650 routing between 8 VLANs for 64 hosts on 8 access switches, plus a "stack".

CORE (3650): `ip routing`, 8 user SVIs (VLAN 10-80) and a management SVI (VLAN 99),
a routed port (g1/0/24, `no switchport`) to EDGE (2911) with a default route, and a
trunk to every access switch on g1/0/1-6.
ACC1-ACC6 (2960s): 8 static PCs each, one per VLAN (48 PCs), management SVI in VLAN 99
with `ip default-gateway`, uplink trunks allowed 10-80,99 only.
STACK1 + STACK2 (3650s): meant as a two-member switch stack. Packet Tracer's 3650 has
no stack ports in pktlib's port list, so the script writes the stack config IOS uses
(`switch 1 priority 15`, `switch 2 provision ws-c3650-24ps`) and joins them with a
two-link LACP channel instead. 16 more PCs hang off them (8 each).

Check in Packet Tracer:
  CORE# show ip route                 -> 8 connected /24s, Vlan99, and S* 0.0.0.0 via EDGE
  PC-1-10 (ACC1, VLAN 10) ping PC-6-80's address (10.0.80.16) -> routed by CORE
  PC-S2-40 ping 192.0.2.1 (EDGE's loopback) -> through CORE's routed port
  ACC3# ping 10.0.99.1                -> management SVI to CORE over the trunk
  STACK1# show switch                 -> whether the `switch` lines did anything (expect not)
  STACK1# show etherchannel summary   -> Po1(SU)
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw06_mls_fanout.pkt"
VLANS = [10, 20, 30, 40, 50, 60, 70, 80]
MGMT = 99
ALLOWED = "10-80,99"
problems: list[str] = []

net = pktlib.new()
core = net.multilayer("CORE", "3650-24PS", at=(900, 80))
edge = net.router("EDGE", "2911", at=(1300, 80))
cfg = [
    "ip routing",
    "spanning-tree mode rapid-pvst",
    "spanning-tree vlan 1-4094 priority 4096",
    "interface g1/0/24",
    " no switchport",
    " ip address 10.255.0.1 255.255.255.252",
    "ip route 0.0.0.0 0.0.0.0 10.255.0.2",
]
for v in VLANS + [MGMT]:
    cfg += [f"vlan {v}", f" name V{v}", f"interface vlan {v}", f" ip address 10.0.{v}.1 255.255.255.0", " no shutdown"]
cfg += ["interface range g1/0/1 - 8", " switchport mode trunk", f" switchport trunk allowed vlan {ALLOWED}"]
core.config(cfg)
core["g1/0/24"].connect(edge["g0/0"])
edge["g0/0"].address = "10.255.0.2/30"
edge.config("interface loopback 0\n ip address 192.0.2.1 255.255.255.255\nip route 10.0.0.0 255.255.0.0 10.255.0.1")

host_no = 10
for a in range(1, 7):
    acc = net.switch(f"ACC{a}", "2960-24TT", at=(80 + (a - 1) * 300, 260))
    acc.config(f"""
spanning-tree mode rapid-pvst
interface g0/1
 switchport mode trunk
 switchport trunk allowed vlan {ALLOWED}
interface vlan 1
 shutdown
interface vlan {MGMT}
 ip address 10.0.{MGMT}.{10 + a} 255.255.255.0
 no shutdown
ip default-gateway 10.0.{MGMT}.1
""")
    acc.add_vlan(MGMT, "MGMT")
    acc["g0/1"].connect(core[f"g1/0/{a}"])
    for i, v in enumerate(VLANS):
        pc = net.pc(
            f"PC-{a}-{v}",
            at=(20 + (a - 1) * 300 + (i % 4) * 70, 400 + (i // 4) * 90),
            ip=f"10.0.{v}.{10 + a}/24",
            gateway=f"10.0.{v}.1",
        )
        acc[f"fa0/{i + 1}"].connect(pc["fa0"])
        acc.config(
            f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {v}\n spanning-tree portfast"
        )

# the "stack": two 3650s that should be one logical switch
stack = [net.multilayer(f"STACK{s}", "3650-24PS", at=(500 + 700 * (s - 1), 700)) for s in (1, 2)]
stack_ports = [p for p in stack[0].ports if "stack" in p.lower()]
if not stack_ports:
    problems.append(
        "3650 has no stack ports in pktlib (ports end at "
        f"{list(stack[0].ports)[-1]}); StackWise can't be cabled, used LACP instead"
    )
for s, sw in enumerate(stack, 1):
    sw.config(f"""
switch 1 priority 15
switch 2 provision ws-c3650-24ps
spanning-tree mode rapid-pvst
interface port-channel 1
 switchport mode trunk
interface range g1/0/23 - 24
 switchport mode trunk
 channel-group 1 mode active
interface g1/1/1
 switchport mode trunk
 switchport trunk allowed vlan {ALLOWED}
""")
    sw["g1/1/1"].connect(core[f"g1/0/{6 + s}"])
    for i, v in enumerate(VLANS):
        pc = net.pc(
            f"PC-S{s}-{v}",
            at=(300 + 700 * (s - 1) + (i % 4) * 90, 820 + (i // 4) * 90),
            ip=f"10.0.{v}.{100 + s}/24",
            gateway=f"10.0.{v}.1",
        )
        sw[f"g1/0/{i + 1}"].connect(pc["fa0"])
        sw.config(
            f"interface g1/0/{i + 1}\n switchport mode access\n switchport access vlan {v}\n spanning-tree portfast"
        )
for p in ("g1/0/23", "g1/0/24"):
    stack[0][p].connect(stack[1][p])

net.around(core, edge, label="L3 core", outline="blue", pad=40)
net.around(*stack, label="intended stack", outline="purple", pad=60)
net.save(OUT)
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
