"""rt01: RIPv2, OSPF and EIGRP redistributed into each other at once.

Stresses: one 2911 (TRIAD, two HWIC-2T cards) running all three protocols
and redistributing each into the other two (six redistribute lines), a
second RIP/OSPF redistribution point on RIP2 with route-map tags to stop
the loop, EIGRP summarisation on an interface, an EIGRP stub router, and
serial cards across four router families (2620XM+WIC-2T, 2811+WIC-2T,
1941+HWIC-2T, ISR4331+NIM-2T).

Check in Packet Tracer:
  - TRIAD `show ip route`: R, O, D, O E2 and D EX routes all present
  - OSPF2 `show ip route`: the EIGRP loopbacks show as ONE O E2 172.20.4.0/22
    summary (EIGRP2 summarises them toward TRIAD), not four /24s
  - EIGRP1 `show ip eigrp neighbors detail`: STUB shows "Stub Peer"
  - RIP2 `show route-map`: both maps exist with match counts
  - PC-RIP1 `ping 172.20.9.10` (PC-STUB, across RIP, TRIAD, EIGRP)
  - PC-OSPF2 `tracert 10.1.1.10` (PC-RIP1): goes via RIP2, not TRIAD
"""

from _common import attempt, finish, host, nw, pktlib, plain, wild, wire

net = pktlib.new()

triad = net.router("TRIAD", "2911", at=(600, 350))
attempt("TRIAD HWIC-2T 0/0", triad.add_module, "HWIC-2T", slot=(0, 0))
attempt("TRIAD HWIC-2T 0/1", triad.add_module, "HWIC-2T", slot=(0, 1))

rip1 = net.router("RIP1", "2620XM", at=(250, 200))
attempt("RIP1 WIC-2T", rip1.add_module, "WIC-2T")
rip2 = net.router("RIP2", "2811", at=(250, 500))
attempt("RIP2 WIC-2T", rip2.add_module, "WIC-2T", slot=(0, 1))  # Serial0/1/0, 0/1/1

ospf1 = net.router("OSPF1", "1841+WIC-2T", at=(600, 100))
ospf2 = net.router("OSPF2", "2911", at=(600, 620))
attempt("OSPF2 HWIC-2T", ospf2.add_module, "HWIC-2T", slot=(0, 3))  # Serial0/3/0, 0/3/1

eig1 = net.router("EIGRP1", "1941", at=(950, 200))
attempt("EIGRP1 HWIC-2T", eig1.add_module, "HWIC-2T")
eig2 = net.router("EIGRP2", "ISR4331", at=(950, 500))
attempt("EIGRP2 NIM-2T", eig2.add_module, "NIM-2T", slot=(0, 2))  # Serial0/2/0, 0/2/1
stub = net.router("STUB", "2811", at=(1250, 200))
attempt("STUB WIC-2T", stub.add_module, "WIC-2T")

L = {  # links
    "T-R1": "10.255.0.0/30",
    "T-O1": "10.255.0.4/30",
    "T-E1": "10.255.0.8/30",
    "T-E2": "10.255.0.12/30",
    "R1-R2": "10.255.0.16/30",
    "R2-O2": "10.255.0.20/30",
    "O1-O2": "10.255.0.24/30",
    "E1-S": "10.255.0.28/30",
    "E1-E2": "10.255.0.32/30",
}
attempt("TRIAD-RIP1", wire, triad, "se0/0/0", rip1, "se0/0", L["T-R1"])
attempt("TRIAD-OSPF1", wire, triad, "se0/0/1", ospf1, "se0/0/0", L["T-O1"])
attempt("TRIAD-EIGRP1", wire, triad, "se0/1/0", eig1, "se0/0/0", L["T-E1"])
attempt("TRIAD-EIGRP2", wire, triad, "se0/1/1", eig2, "se0/2/0", L["T-E2"])
attempt("RIP1-RIP2", wire, rip1, "se0/1", rip2, "se0/1/0", L["R1-R2"])
attempt("RIP2-OSPF2", wire, rip2, "se0/1/1", ospf2, "se0/3/0", L["R2-O2"])
attempt("OSPF1-OSPF2", wire, ospf1, "se0/0/1", ospf2, "se0/3/1", L["O1-O2"])
attempt("EIGRP1-STUB", wire, eig1, "se0/0/1", stub, "se0/0/0", L["E1-S"])
attempt("EIGRP1-EIGRP2 (gig)", wire, eig1, "g0/1", eig2, "g0/0/1", L["E1-E2"])

LAN = {
    "RIP1": "10.1.1.0/24",
    "RIP2": "10.1.2.0/24",
    "OSPF1": "10.2.1.0/24",
    "OSPF2": "10.2.2.0/24",
    "EIGRP1": "172.20.1.0/24",
    "EIGRP2": "172.20.8.0/24",
    "STUB": "172.20.9.0/24",
}
LAN_PORT = {
    "RIP1": "fa0/0",
    "RIP2": "fa0/0",
    "OSPF1": "fa0/0",
    "OSPF2": "g0/0",
    "EIGRP1": "g0/0",
    "EIGRP2": "g0/0/0",
    "STUB": "fa0/0",
}
for r in (rip1, rip2, ospf1, ospf2, eig1, eig2, stub):
    cidr = LAN[r.name]
    x, y = r.xy
    pc = net.pc(f"PC-{r.name}", at=(x + (-120 if x < 600 else 120), y + 60), ip=host(cidr, 10), gateway=plain(cidr, 1))
    r[LAN_PORT[r.name]].connect(pc["fa0"])
    r[LAN_PORT[r.name]].address = host(cidr, 1)

# --- RIP domain -------------------------------------------------------------
rip1.config("""
router rip
 version 2
 no auto-summary
 network 10.0.0.0
 passive-interface FastEthernet0/0
""")
# RIP2 is the second RIP/OSPF border: tag what it redistributes, refuse what
# came the other way already tagged (the classic two-point mutual redistribution loop)
rip2.config(f"""
route-map OSPF-TO-RIP deny 10
 match tag 120
route-map OSPF-TO-RIP permit 20
 set tag 110
route-map RIP-TO-OSPF deny 10
 match tag 110
route-map RIP-TO-OSPF permit 20
 set tag 120
router rip
 version 2
 no auto-summary
 network 10.0.0.0
 passive-interface FastEthernet0/0
 passive-interface Serial0/1/1
 redistribute ospf 1 metric 5 route-map OSPF-TO-RIP
router ospf 1
 router-id 2.2.2.2
 network {wild(L["R2-O2"])} area 0
 redistribute rip subnets route-map RIP-TO-OSPF
""")

# --- OSPF domain ------------------------------------------------------------
for r, rid in ((ospf1, "3.3.3.1"), (ospf2, "3.3.3.2")):
    r.config(
        f"router ospf 1\n router-id {rid}\n network {wild(LAN[r.name])} area 0\n"
        f" passive-interface {r[LAN_PORT[r.name]].name}"
    )
ospf1.config(f"router ospf 1\n network {wild(L['T-O1'])} area 0\n network {wild(L['O1-O2'])} area 0")
ospf2.config(f"router ospf 1\n network {wild(L['R2-O2'])} area 0\n network {wild(L['O1-O2'])} area 0")

# --- EIGRP domain -----------------------------------------------------------
eig1.config(f"""
router eigrp 100
 eigrp router-id 4.4.4.1
 no auto-summary
 network {wild(L["T-E1"])}
 network {wild(L["E1-S"])}
 network {wild(L["E1-E2"])}
 network {wild(LAN["EIGRP1"])}
 passive-interface GigabitEthernet0/0
""")
loops = [f"172.20.{4 + i}.0/24" for i in range(4)]
eig2.config(
    "".join(f"interface loopback {i}\n ip address {plain(c, 1)} {nw(c).netmask}\n" for i, c in enumerate(loops))
)
eig2.config(f"""
interface Serial0/2/0
 ip summary-address eigrp 100 172.20.4.0 255.255.252.0
router eigrp 100
 eigrp router-id 4.4.4.2
 no auto-summary
 network {wild(L["T-E2"])}
 network {wild(L["E1-E2"])}
 network 172.20.4.0 0.0.3.255
 network {wild(LAN["EIGRP2"])}
""")
stub.config(f"""
router eigrp 100
 eigrp router-id 4.4.4.9
 no auto-summary
 network {wild(L["E1-S"])}
 network {wild(LAN["STUB"])}
 eigrp stub connected
""")

# --- TRIAD: all three, each into the other two ------------------------------
triad.config(f"""
interface loopback 0
 ip address 9.9.9.9 255.255.255.255
router rip
 version 2
 no auto-summary
 network 10.0.0.0
 passive-interface Serial0/0/1
 redistribute ospf 1 metric 3
 redistribute eigrp 100 metric 4
router ospf 1
 router-id 9.9.9.9
 network {wild(L["T-O1"])} area 0
 network 9.9.9.9 0.0.0.0 area 0
 redistribute rip subnets
 redistribute eigrp 100 subnets metric 50 metric-type 1
router eigrp 100
 eigrp router-id 9.9.9.9
 no auto-summary
 network {wild(L["T-E1"])}
 network {wild(L["T-E2"])}
 redistribute rip metric 1544 20000 255 1 1500
 redistribute ospf 1 metric 1544 20000 255 1 1500
""")
# RIP's `network 10.0.0.0` on TRIAD also catches the OSPF-side serial, hence
# the passive-interface. Checked: TRIAD's running config keeps three router blocks.
blocks = [l for l in triad.running_config if l.startswith("router ")]
print("TRIAD router blocks:", blocks)

net.around(rip1, rip2, "PC-RIP1", "PC-RIP2", shape="ellipse", outline="orange", label="RIPv2")
net.around(ospf1, ospf2, "PC-OSPF1", "PC-OSPF2", shape="ellipse", outline="blue", label="OSPF 1 area 0")
net.around(eig1, eig2, stub, "PC-EIGRP1", "PC-EIGRP2", "PC-STUB", shape="ellipse", outline="green", label="EIGRP 100")
finish(net, "rt01_three_protocols")
