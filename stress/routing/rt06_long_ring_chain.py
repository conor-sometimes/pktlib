"""rt06: a 12-router serial ring of mixed hardware plus a 14-router RIP chain.

Stresses: twelve different router/card combinations in one OSPF ring
(1841+WIC-2T, 2811+WIC-2T, 2911+HWIC-2T, ISR4331+NIM-2T, 1941+HWIC-2T,
2620XM+WIC-2T, Router-PT built-in serials, 2901+HWIC-2T, 1841 with two WIC-1T,
2621XM+WIC-2T, ISR4321+NIM-2T, 2811 with two WIC-1T), so serial cables join
smart-serial and plain serial ports; a 14-router RIPv2 chain (Ethernet,
cross-over) hanging off RING1, redistributed both ways, so the far end sits
14 RIP hops out, one short of RIP's limit; a LAN with a secondary address.

Check in Packet Tracer:
  - every ring link up: RING1 `show ip ospf neighbor` shows RING2 and RING12
  - CHAIN14 `show ip route rip`: the ring LANs at metric 14 (not 16/unreachable)
  - PC-CHAIN14 `tracert 10.60.7.10` (PC-RING7): 14 chain hops then the ring
  - PC-RING4B (on RING4's secondary subnet) `ping 10.60.10.10`
  - RING7 (Router-PT) `show controllers serial 2/0`: cable type DCE/DTE as drawn
"""

import math

from _common import attempt, finish, host, note, pktlib, plain, wild, wire

net = pktlib.new()

RING = [  # (model, cards to fit [(module, slot)])
    ("1841+WIC-2T", []),
    ("2811", [("WIC-2T", (0, 0))]),
    ("2911", [("HWIC-2T", (0, 0))]),
    ("ISR4331", [("NIM-2T", (0, 1))]),
    ("1941", [("HWIC-2T", (0, 1))]),
    ("2620XM", [("WIC-2T", (0, 0))]),
    ("Router-PT", []),
    ("2901", [("HWIC-2T", (0, 2))]),
    ("1841", [("WIC-1T", (0, 0)), ("WIC-1T", (0, 1))]),
    ("2621XM", [("WIC-2T", (0, 1))]),
    ("ISR4321", [("NIM-2T", (0, 2))]),
    ("2811", [("WIC-1T", (0, 2)), ("WIC-1T", (0, 3))]),
]
N = len(RING)
cx, cy, rad = 900, 700, 450
ring = []
for i, (model, cards) in enumerate(RING):
    ang = 2 * math.pi * i / N - math.pi / 2
    r = net.router(f"RING{i + 1}", model, at=(round(cx + rad * math.cos(ang)), round(cy + rad * math.sin(ang))))
    for mod, slot in cards:
        attempt(f"RING{i + 1} {model} + {mod} in {slot}", r.add_module, mod, slot=slot)
    serials = sorted(p for p in r.ports if p.startswith("Serial"))
    lan = next(p for p in r.ports if p.startswith(("FastEthernet", "GigabitEthernet")))
    print(f"RING{i + 1} {model}: serials {serials}, LAN on {lan}")
    ring.append((r, serials, lan, ang))

for i, (r, serials, _lan, _ang) in enumerate(ring):
    nxt, nserials, _, _ = ring[(i + 1) % N]
    cidr = f"10.255.{i}.0/30"
    if len(serials) < 2 or len(nserials) < 2:
        note(f"{r.name} or {nxt.name} has fewer than two serial ports")
        continue
    attempt(
        f"ring {r.name}.{serials[0]} -> {nxt.name}.{nserials[1]}", wire, r, serials[0], nxt, nserials[1], cidr, 128000
    )
    r.config(f"router ospf 1\n network {wild(cidr)} area 0")
    nxt.config(f"router ospf 1\n network {wild(cidr)} area 0")

for i, (r, _, lan, ang) in enumerate(ring):
    cidr = f"10.60.{i + 1}.0/24"
    r[lan].address = host(cidr, 1)
    r.config(
        f"router ospf 1\n router-id 10.255.255.{i + 1}\n network {wild(cidr)} area 0\n passive-interface {r[lan].name}"
    )
    x, y = r.xy
    ox, oy = math.cos(ang), math.sin(ang)
    sw = net.switch(f"SW-RING{i + 1}", at=(round(x + 120 * ox), round(y + 120 * oy)))
    r[lan].connect(sw["fa0/1"])
    pc = net.pc(
        f"PC-RING{i + 1}", at=(round(x + 220 * ox), round(y + 220 * oy)), ip=host(cidr, 10), gateway=plain(cidr, 1)
    )
    sw["fa0/2"].connect(pc["fa0"])
    if i == 3:
        # a second subnet on the same LAN via a secondary address
        r.config(
            f"interface {r[lan].name}\n ip address 10.61.4.1 255.255.255.0 secondary\n"
            "router ospf 1\n network 10.61.4.0 0.0.0.255 area 0"
        )
        pcb = net.pc(
            "PC-RING4B", at=(round(x + 220 * ox + 80), round(y + 220 * oy)), ip="10.61.4.10/24", gateway="10.61.4.1"
        )
        sw["fa0/3"].connect(pcb["fa0"])
        print("RING4 LAN as pktlib reads it (should be the primary 10.60.4.1/24):", r[lan].address)
        if r[lan].address != host(cidr, 1):
            note(
                f"secondary address read as the primary: {r.name}.{r[lan].name}.address is {r[lan].address}; "
                "iosconfig.interface_state takes any `ip address` line, `secondary` included"
            )

# --- the RIP chain, off RING1 -----------------------------------------------
CHAIN = 14
r1, _, _, _ = ring[0]
r1_free = next(p for p in r1.ports if p.startswith("FastEthernet") and not r1[p].link)
prev, prev_port = r1, r1_free
chain = []
for k in range(CHAIN):
    model = ("2901", "2911", "1941")[k % 3]
    c = net.router(f"CHAIN{k + 1}", model, at=(900 - 60 * k, 120 - 40 * (k % 2)))
    cidr = f"10.70.{k}.0/30"
    attempt(f"chain link {prev.name}-{c.name}", wire, prev, prev_port, c, "g0/0", cidr)
    c.config("router rip\n version 2\n no auto-summary\n network 10.0.0.0")
    chain.append(c)
    prev, prev_port = c, "g0/1"
r1.config(f"""
router rip
 version 2
 no auto-summary
 passive-interface default
 no passive-interface {r1[r1_free].name}
 network 10.0.0.0
 redistribute ospf 1 metric 1
router ospf 1
 redistribute rip subnets
""")
last = chain[-1]
last["g0/1"].address = "10.80.0.1/24"
pc_far = net.pc("PC-CHAIN14", at=(last.xy[0] - 120, last.xy[1]), ip="10.80.0.10/24", gateway="10.80.0.1")
last["g0/1"].connect(pc_far["fa0"])

cables = {}
for l in net.links:
    cables[l.cable] = cables.get(l.cable, 0) + 1
print("cables:", cables)
net.around(*chain, pc_far, shape="rectangle", outline="orange", label="RIPv2 chain, 14 hops")
finish(net, "rt06_long_ring_chain")
