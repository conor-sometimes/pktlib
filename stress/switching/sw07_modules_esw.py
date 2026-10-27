"""Stress: switch modules in routers (HWIC-4ESW), HSRP on router SVIs, power supplies, refused cards.

BR-A and BR-B (1941s) each get two HWIC-4ESW cards (8 router switch ports,
Fa0/0/0-3 and Fa0/1/0-3). Each router has `vlan 10`/`vlan 20` and SVIs Vlan10 and
Vlan20 with HSRP between the two routers (BR-A active on 10, BR-B on 20). The
routers are joined by a trunk between their Fa0/1/3 ports, and each has three PCs
on its EtherSwitch ports (no separate switch at all). G0/0 on each router is a
routed uplink to WAN (a 2901 with four HWIC-4ESW cards, 16 router switch ports, a
PC on every one of them in VLAN 30, Vlan30 as their gateway) and OSPF runs over it.
Hardware tried as well, each attempt reported if pktlib refuses it:
  CORE (3650): a second AC-POWER-SUPPLY (should fit), a third (should be refused),
               a GLC-T SFP (the Physical tab lists it)
  ISR (ISR4331): NIM-ES2-4 (the Physical tab lists it)
  OLD (2811): NM-ESW-161 (the Physical tab lists it)
  SWPT (Switch-PT): PT-SWITCH-NM-1CGE (the Physical tab lists it)

Check in Packet Tracer:
  BR-A# show standby brief         -> Vlan10 Active, Vlan20 Standby (BR-B the reverse)
  BR-A# show vlan-switch (or show vlan brief) -> VLAN 10 and 20 exist on the router
  BR-A# show interfaces status / show ip interface brief -> Fa0/0/x and Fa0/1/x up, not admin down
  PC-A1 (VLAN 10 on BR-A) ping PC-B3 (VLAN 20 on BR-B) -> via the HSRP gateways
  PC-W1 (on WAN's HWIC ports) ping PC-A1     -> over OSPF on the routed uplinks
  Links from HWIC-4ESW ports to PCs: are they green? pktlib draws them with a cross-over cable
  CORE Physical tab: two power supplies fitted
"""

from pathlib import Path

import pktlib
from pktlib import PktError

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw07_modules_esw.pkt"
problems: list[str] = []


def attempt(what: str, fn):
    try:
        return fn()
    except PktError as e:
        problems.append(f"{what}: PktError: {e}")
        return None


net = pktlib.new()

# --- branch routers with EtherSwitch cards ---------------------------------
brs = []
for b, tag in enumerate("AB"):
    r = net.router(f"BR-{tag}", "1941", at=(300 + 600 * b, 380))
    attempt(f"BR-{tag}.add_module('HWIC-4ESW') #1", lambda r=r: r.add_module("HWIC-4ESW"))
    attempt(f"BR-{tag}.add_module('HWIC-4ESW') #2", lambda r=r: r.add_module("HWIC-4ESW"))
    me = 2 + b
    cfg = ["vlan 10", " name TEN", "vlan 20", " name TWENTY"]
    for v in (10, 20):
        active = (v == 10) == (b == 0)
        cfg += [
            f"interface vlan {v}",
            f" ip address 10.7.{v}.{me} 255.255.255.0",
            f" standby {v} ip 10.7.{v}.1",
            f" standby {v} priority {150 if active else 100}",
            f" standby {v} preempt",
            " no shutdown",
        ]
    for i, v in enumerate((10, 10, 20)):
        cfg += [f"interface fa0/0/{i}", " switchport mode access", f" switchport access vlan {v}", " no shutdown"]
    cfg += [
        "interface fa0/1/3",
        " switchport mode trunk",
        " no shutdown",
        "interface g0/0",
        f" ip address 10.7.255.{4 * b + 2} 255.255.255.252",
        " no shutdown",
        "router ospf 1",
        f" network 10.7.255.{4 * b} 0.0.0.3 area 0",
        " network 10.7.10.0 0.0.0.255 area 0",
        " network 10.7.20.0 0.0.0.255 area 0",
    ]
    r.config(cfg)
    if 10 not in r.vlans:
        problems.append(
            f"BR-{tag}: `vlan 10` in config() stayed in the running config, not the router's "
            f"VLAN database (r.vlans = {sorted(x for x in r.vlans if x < 1000)}); "
            "add_vlan() on the same router works"
        )
    for i, v in enumerate((10, 10, 20)):
        pc = net.pc(
            f"PC-{tag}{i + 1}",
            at=(150 + 600 * b + 110 * i, 540),
            ip=f"10.7.{v}.{10 * (b + 1) + i}/24",
            gateway=f"10.7.{v}.1",
        )
        link = r[f"fa0/0/{i}"].connect(pc["fa0"])
        if i == 0:
            print(f"BR-{tag}.Fa0/0/0 -> PC cable picked: {link.cable}")
    brs.append(r)
brs[0]["fa0/1/3"].connect(brs[1]["fa0/1/3"])

# --- WAN router: four EtherSwitch cards ------------------------------------
wan = net.router("WAN", "2901", at=(600, 220))
for k in range(4):
    attempt(f"WAN.add_module('HWIC-4ESW') #{k + 1}", lambda: wan.add_module("HWIC-4ESW"))
esw = [p for p in wan.ports if p.startswith("FastEthernet0/")]
print(f"WAN EtherSwitch ports: {len(esw)} ({esw[0]} .. {esw[-1]})" if esw else "WAN has no EtherSwitch ports")
cfg = [
    "vlan 30",
    " name THIRTY",
    "interface vlan 30",
    " ip address 10.7.30.1 255.255.255.0",
    " no shutdown",
    "interface g0/0",
    " ip address 10.7.255.1 255.255.255.252",
    " no shutdown",
    "interface g0/1",
    " ip address 10.7.255.5 255.255.255.252",
    " no shutdown",
    "router ospf 1",
    " network 10.7.255.0 0.0.0.7 area 0",
    " network 10.7.30.0 0.0.0.255 area 0",
]
for p in esw:
    cfg += [f"interface {p}", " switchport mode access", " switchport access vlan 30", " no shutdown"]
wan.config(cfg)
wan["g0/0"].connect(brs[0]["g0/0"])
wan["g0/1"].connect(brs[1]["g0/0"])
for i, p in enumerate(esw):
    pc = net.pc(f"PC-W{i + 1}", at=(80 + 75 * i, 40 if i % 2 else 110), ip=f"10.7.30.{10 + i}/24", gateway="10.7.30.1")
    wan[p].connect(pc["fa0"])

# --- hardware that may or may not fit ---------------------------------------
core = net.multilayer("CORE", "3650-24PS", at=(1300, 250))
attempt("CORE.add_module('AC-POWER-SUPPLY') (second)", lambda: core.add_module("AC-POWER-SUPPLY"))
attempt("CORE.add_module('AC-POWER-SUPPLY') (third, expected refused)", lambda: core.add_module("AC-POWER-SUPPLY"))
attempt("CORE.add_module('GLC-T')", lambda: core.add_module("GLC-T"))
print("CORE modules:", core.modules)
isr = net.router("ISR", "ISR4331", at=(1300, 400))
attempt("ISR.add_module('NIM-ES2-4')", lambda: isr.add_module("NIM-ES2-4"))
old = net.router("OLD", "2811", at=(1450, 400))
attempt("OLD.add_module('NM-ESW-161')", lambda: old.add_module("NM-ESW-161"))
swpt = net.switch("SWPT", "Switch-PT", at=(1450, 250))
attempt("SWPT.add_module('PT-SWITCH-NM-1CGE')", lambda: swpt.add_module("PT-SWITCH-NM-1CGE"))
acc = net.switch("ACC", "2960-24TT", at=(1600, 250))
attempt("ACC (2960).add_module('AC-POWER-SUPPLY'), expected refused", lambda: acc.add_module("AC-POWER-SUPPLY"))

net.around(*brs, label="HSRP on router SVIs", outline="green", pad=40)
net.save(OUT)
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
