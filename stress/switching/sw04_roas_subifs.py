"""Stress: router-on-a-stick with 24 sub-interfaces over two trunks, DHCP from the router.

ROUTER (2911):
  g0/0   trunk to SW-A: 16 sub-interfaces, g0/0.10 .. g0/0.160, plus g0/0.99 as the
         native VLAN (`encapsulation dot1Q 99 native`), one sub-interface with a
         secondary address (g0/0.10 also answers on 172.16.10.1/24)
  g0/1   trunk to SW-B: 8 more sub-interfaces, g0/1.210 .. g0/1.280
  DHCP   a pool per VLAN on the router itself (24 pools; none for native 99)
SW-A and SW-C (2960s) daisy-chain on a trunk, so VLANs 10-160 span both; SW-B holds
VLANs 210-280 (172.20.x.0/24). Native VLAN 99 on every trunk to match g0/0.99. 40 DHCP PCs.

Check in Packet Tracer:
  ROUTER# show ip interface brief     -> 25 sub-interfaces up/up on g0/0 and g0/1
  ROUTER# show vlans                  -> VLAN 99 listed as native on g0/0.99
  PC-A-V10 DHCP -> 10.10.0.x; PC-C-V160 -> 10.160.0.x (via SW-A's trunk); PC-B-V280 -> 172.20.80.x
  PC-A-V10 ping the address PC-B-V280 got   -> routed across the two trunks
  PC-A-V10 ping 172.16.10.1                 -> the secondary on g0/0.10
  ROUTER# show ip dhcp binding         -> 40 bindings
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw04_roas_subifs.pkt"
A_VLANS = list(range(10, 170, 10))  # 16 VLANs on g0/0
B_VLANS = list(range(210, 290, 10))  # 8 VLANs on g0/1
NATIVE = 99
problems: list[str] = []

net = pktlib.new()
r = net.router("ROUTER", "2911", at=(600, 80))
cfg = [
    "interface g0/0",
    " no shutdown",
    "interface g0/1",
    " no shutdown",
    f"interface g0/0.{NATIVE}",
    f" encapsulation dot1Q {NATIVE} native",
    f" ip address 10.{NATIVE}.0.1 255.255.255.0",
]
for port, vids in (("g0/0", A_VLANS), ("g0/1", B_VLANS)):
    for v in vids:
        pre = f"10.{v}.0" if v < 200 else f"172.20.{v - 200}"
        cfg += [f"interface {port}.{v}", f" encapsulation dot1Q {v}", f" ip address {pre}.1 255.255.255.0"]
        if v == 10:
            cfg += [" ip address 172.16.10.1 255.255.255.0 secondary"]
        cfg += [
            f"ip dhcp excluded-address {pre}.1 {pre}.9",
            f"ip dhcp pool V{v}",
            f" network {pre}.0 255.255.255.0",
            f" default-router {pre}.1",
        ]
r.config(cfg)

# what does pktlib think g0/0.10's address is? It should be the primary, 10.10.0.1/24
got = r.interfaces.get("GigabitEthernet0/0.10")
if not got or got[0] != "10.10.0.1/24":
    problems.append(
        f"ROUTER.interfaces['GigabitEthernet0/0.10'] reads {got}, want primary 10.10.0.1/24 "
        "(the `secondary` line was taken as the primary)"
    )

swa = net.switch("SW-A", "2960-24TT", at=(350, 260))
swb = net.switch("SW-B", "2960-24TT", at=(900, 260))
swc = net.switch("SW-C", "2960-24TT", at=(350, 460))
for sw in (swa, swb, swc):
    sw.add_vlan(NATIVE, "NATIVE")
trunk = f" switchport mode trunk\n switchport trunk native vlan {NATIVE}"
r["g0/0"].connect(swa["g0/1"])
r["g0/1"].connect(swb["g0/1"])
swa["g0/2"].connect(swc["g0/1"])
swa.config(f"interface g0/1\n{trunk}\ninterface g0/2\n{trunk}")
swc.config(f"interface g0/1\n{trunk}")
swb.config(f"interface g0/1\n{trunk}")

placements = [(swa, "A", A_VLANS, 40), (swc, "C", A_VLANS, 40), (swb, "B", B_VLANS, 700)]
for sw, tag, vids, x0 in placements:
    y0 = 600 if sw is swc else 400
    for i, v in enumerate(vids):
        pc = net.pc(f"PC-{tag}-V{v}", at=(x0 + (i % 8) * 70, y0 + (i // 8) * 90))
        pc.use_dhcp()
        sw[f"fa0/{i + 1}"].connect(pc["fa0"])
        sw.config(f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {v}")

net.save(OUT)
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
