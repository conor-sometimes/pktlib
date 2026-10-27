"""rt02: multi-area OSPF with every area type and a virtual link.

Stresses: area 0 triangle with interface MD5 authentication and a broadcast
segment where DR priority is set; area 1 stub with an `area range` summary;
area 2 totally stubby (`stub no-summary` on the ABR only); area 3 NSSA with
an ASBR redistributing connected loopbacks and a static, summarised with
`summary-address`; area 4 a normal transit area; area 5 hanging off area 4
with no touch to area 0, joined by a virtual link through area 4.
Hardware: ISR4331 with two NIM-2T, 2911 with two HWIC-2T, 2811 with two
WIC-2T, 1841+WIC-2T with a second WIC-2T, 2620XM+WIC-2T, 1941+HWIC-2T.
`passive-interface default` on CORE, `auto-cost reference-bandwidth` everywhere.

Check in Packet Tracer:
  - TS2 `show ip route ospf`: only intra-area routes and `O*IA 0.0.0.0/0`
  - STB1 `show ip route ospf`: O IA routes plus `O*IA 0.0.0.0/0`, no O E2
  - CORE `show ip route`: `O IA 10.11.0.0/22` (area 1 range) and
    `O E2 192.168.48.0/22` (the NSSA summary, translated to type 5)
  - ABR-B `show ip route`: `O N2 192.168.48.0/22`
  - ABR-C and T4 `show ip ospf virtual-links`: state POINT_TO_POINT / FULL
  - V5 `show ip route`: O IA routes from areas 1-3 (only possible over the virtual link)
  - PC-V5 `ping 10.12.0.10` (PC-TS2), PC-CORE `ping 10.15.0.10` (PC-V5)
  - CORE `show ip ospf neighbor`: ABR-B is DROTHER on the LAN (priority 0)
"""

from _common import attempt, finish, host, pktlib, plain, wild, wire

net = pktlib.new()
REF = " auto-cost reference-bandwidth 1000"

abr_a = net.router("ABR-A", "ISR4331", at=(400, 300))
attempt("ABR-A NIM-2T 0/1", abr_a.add_module, "NIM-2T", slot=(0, 1))
attempt("ABR-A NIM-2T 0/2", abr_a.add_module, "NIM-2T", slot=(0, 2))
attempt("ABR-A third NIM-2T (no slot left)", abr_a.add_module, "NIM-2T")  # expect a refusal

abr_b = net.router("ABR-B", "2911", at=(800, 300))
attempt("ABR-B HWIC-2T 0/0", abr_b.add_module, "HWIC-2T", slot=(0, 0))
attempt("ABR-B HWIC-2T 0/2", abr_b.add_module, "HWIC-2T", slot=(0, 2))

core = net.router("CORE", "2811", at=(600, 150))
attempt("CORE WIC-2T 0/0", core.add_module, "WIC-2T", slot=(0, 0))
attempt("CORE WIC-2T 0/1", core.add_module, "WIC-2T", slot=(0, 1))

abr_c = net.router("ABR-C", "1841+WIC-2T", at=(600, 450))
attempt("ABR-C second WIC-2T", abr_c.add_module, "WIC-2T", slot=(0, 1))

stb1 = net.router("STB1", "1841", at=(150, 150))
attempt("STB1 WIC-2T", stb1.add_module, "WIC-2T")
ts2 = net.router("TS2", "2620XM", at=(150, 450))
attempt("TS2 WIC-2T", ts2.add_module, "WIC-2T")
n3 = net.router("NSSA3", "2811", at=(1050, 150))
attempt("NSSA3 WIC-2T", n3.add_module, "WIC-2T", slot=(0, 2))
t4 = net.router("T4", "2911", at=(600, 650))
attempt("T4 HWIC-2T", t4.add_module, "HWIC-2T", slot=(0, 1))
v5 = net.router("V5", "1941", at=(900, 650))
attempt("V5 HWIC-2T", v5.add_module, "HWIC-2T", slot=(0, 1))

RID = {
    abr_a: "1.1.1.1",
    abr_b: "1.1.1.2",
    abr_c: "1.1.1.3",
    core: "1.1.1.10",
    stb1: "2.2.2.1",
    ts2: "2.2.2.2",
    n3: "2.2.2.3",
    t4: "4.4.4.4",
    v5: "5.5.5.5",
}
for r, rid in RID.items():
    r.config(f"interface loopback 0\n ip address {rid} 255.255.255.255\nrouter ospf 1\n router-id {rid}\n{REF}")

AUTH = " ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 LAB-OSPF"


def area_link(a, ap, b, bp, cidr, area, auth=False):
    attempt(f"{a.name}.{ap}-{b.name}.{bp}", wire, a, ap, b, bp, cidr)
    for r, p in ((a, ap), (b, bp)):
        r.config(f"router ospf 1\n network {wild(cidr)} area {area}")
        if auth:
            r.config(f"interface {r[p].name}\n{AUTH}")


# area 0 triangle (serial) plus a LAN segment between CORE and ABR-B
area_link(core, "se0/0/0", abr_a, "se0/1/0", "10.0.0.0/30", 0, auth=True)
area_link(core, "se0/0/1", abr_b, "se0/0/0", "10.0.0.4/30", 0, auth=True)
area_link(abr_a, "se0/1/1", abr_c, "se0/0/0", "10.0.0.8/30", 0, auth=True)
area_link(abr_b, "se0/0/1", abr_c, "se0/0/1", "10.0.0.12/30", 0, auth=True)

sw0 = net.switch("SW-AREA0", at=(750, 50))
core["fa0/0"].connect(sw0["fa0/1"])
abr_b["g0/0"].connect(sw0["fa0/2"])
core["fa0/0"].address = "10.0.10.1/24"
abr_b["g0/0"].address = "10.0.10.2/24"
pc_core = net.pc("PC-CORE", at=(900, 50), ip="10.0.10.10/24", gateway="10.0.10.1")
sw0["fa0/3"].connect(pc_core["fa0"])
core.config(f"interface fa0/0\n ip ospf priority 200\n{AUTH}\nrouter ospf 1\n network 10.0.10.0 0.0.0.255 area 0")
abr_b.config(f"interface g0/0\n ip ospf priority 0\n{AUTH}\nrouter ospf 1\n network 10.0.10.0 0.0.0.255 area 0")
core.config("""
router ospf 1
 passive-interface default
 no passive-interface Serial0/0/0
 no passive-interface Serial0/0/1
 no passive-interface FastEthernet0/0
 network 1.1.1.10 0.0.0.0 area 0
""")
for r in (abr_a, abr_b, abr_c):
    r.config(f"router ospf 1\n network {RID[r]} 0.0.0.0 area 0")

# area 1: stub, four loopbacks summarised by the ABR
area_link(abr_a, "se0/2/0", stb1, "se0/0/0", "10.1.255.0/30", 1)
stb1.config(
    "".join(
        f"interface loopback {10 + i}\n ip address 10.11.{i}.1 255.255.255.0\n ip ospf network point-to-point\n"
        for i in range(4)
    )
)
stb1.config(f"router ospf 1\n area 1 stub\n network 10.11.0.0 0.0.3.255 area 1\n network {RID[stb1]} 0.0.0.0 area 1")
abr_a.config("router ospf 1\n area 1 stub\n area 1 range 10.11.0.0 255.255.252.0")

# area 2: totally stubby
area_link(abr_a, "se0/2/1", ts2, "se0/0", "10.2.255.0/30", 2)
abr_a.config("router ospf 1\n area 2 stub no-summary")
ts2.config(f"router ospf 1\n area 2 stub\n network {RID[ts2]} 0.0.0.0 area 2")

# area 3: NSSA, ASBR redistributes connected loopbacks and a static
area_link(abr_b, "se0/2/0", n3, "se0/2/0", "10.3.255.0/30", 3)
abr_b.config("router ospf 1\n area 3 nssa")
n3.config("".join(f"interface loopback {20 + i}\n ip address 192.168.{48 + i}.1 255.255.255.0\n" for i in range(4)))
n3.config(f"""
ip route 192.168.51.128 255.255.255.128 Null0
router ospf 1
 area 3 nssa
 network {RID[n3]} 0.0.0.0 area 3
 redistribute connected subnets
 redistribute static subnets
 summary-address 192.168.48.0 255.255.252.0
""")

# area 4 transit, area 5 behind it via a virtual link
area_link(abr_c, "se0/1/0", t4, "se0/1/0", "10.4.255.0/30", 4)
area_link(t4, "se0/1/1", v5, "se0/1/0", "10.5.255.0/30", 5)
abr_c.config(f"router ospf 1\n area 4 virtual-link {RID[t4]}\n area 4 range 10.4.0.0 255.255.0.0")
t4.config(f"router ospf 1\n area 4 virtual-link {RID[abr_c]}\n network {RID[t4]} 0.0.0.0 area 4")
v5.config(f"router ospf 1\n network {RID[v5]} 0.0.0.0 area 5")

# a LAN with a PC on each non-backbone router
LANS = {
    stb1: ("fa0/0", "10.11.8.0/24", 1),
    ts2: ("fa0/0", "10.12.0.0/24", 2),
    n3: ("fa0/0", "10.13.0.0/24", 3),
    t4: ("g0/0", "10.4.1.0/24", 4),
    v5: ("g0/0", "10.15.0.0/24", 5),
}
for r, (port, cidr, area) in LANS.items():
    x, y = r.xy
    pc = net.pc(f"PC-{r.name}", at=(x, y + 110), ip=host(cidr, 10), gateway=plain(cidr, 1))
    r[port].connect(pc["fa0"])
    r[port].address = host(cidr, 1)
    r.config(f"router ospf 1\n network {wild(cidr)} area {area}\n passive-interface {r[port].name}")
stb1.config("router ospf 1\n network 10.11.8.0 0.0.0.255 area 1")  # outside the /22 range on purpose

net.around(core, abr_a, abr_b, abr_c, sw0, pc_core, shape="rectangle", outline="blue", label="AREA 0")
net.around(stb1, "PC-STB1", shape="ellipse", outline="green", label="AREA 1 stub")
net.around(ts2, "PC-TS2", shape="ellipse", outline="green", label="AREA 2 totally stubby")
net.around(n3, "PC-NSSA3", shape="ellipse", outline="orange", label="AREA 3 NSSA")
net.around(t4, "PC-T4", shape="ellipse", outline="grey", label="AREA 4 transit")
net.around(v5, "PC-V5", shape="ellipse", outline="red", label="AREA 5 (virtual link)")
finish(net, "rt02_ospf_areas")
