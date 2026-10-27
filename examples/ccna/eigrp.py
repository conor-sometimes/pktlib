"""EIGRP on three routers, with a fast path, a slow serial backup and a feasible successor.

    uv run python examples/ccna/eigrp.py        # writes eigrp.pkt

R1, R2 and R3 form a triangle in EIGRP autonomous system 100. R1 reaches R3's
LAN two ways: over Ethernet through R2 (fast, the successor) or straight across
a 64 kbit/s serial link (slow). The serial path's reported distance (R3's own
distance to its LAN) is lower than the best path's feasible distance, so it
passes the feasibility condition and sits in the topology table as a feasible
successor, ready to take over without a query.

Config shown: `router eigrp 100`, `eigrp router-id`, `no auto-summary`,
`network` with wildcard masks, `passive-interface` on the LANs, and
`bandwidth` on the serial links so the metric reflects the slow line.

Check in Packet Tracer:
  - R1 `show ip eigrp neighbors`: R2 on Fa0/1 and R3 on Se0/0/0
  - R1 `show ip route eigrp`: D 192.168.3.0/24 [90/...] via 10.0.12.2 (R2), not
    via the serial link
  - R1 `show ip eigrp topology`: 192.168.3.0/24 lists two paths, via
    10.0.12.2 (successor) and via 10.0.13.2 (feasible successor)
  - On R1 `interface fa0/1`, `shutdown`: the route moves to Serial0/0/0
    straight away, and PC1 `ping 192.168.3.10` still works
"""

import pktlib

net = pktlib.new()

r1 = net.router("R1", "1841+WIC-2T", at=(250, 250))
r2 = net.router("R2", "2911", at=(600, 100))
r3 = net.router("R3", "2911", at=(600, 400))
r3.add_module("HWIC-2T")  # Serial0/0/0, 0/0/1 for the slow link to R1

LINKS = [  # (a, port, b, port, subnet)
    (r1, "fa0/1", r2, "g0/1", "10.0.12"),
    (r2, "g0/2", r3, "g0/2", "10.0.23"),
    (r1, "se0/0/0", r3, "se0/0/0", "10.0.13"),
]
for a, ap, b, bp, sub in LINKS:
    a[ap].connect(b[bp])
    a[ap].address = f"{sub}.1/24"
    b[bp].address = f"{sub}.2/24"
r1.config("interface se0/0/0\n clock rate 64000\n bandwidth 64")
r3.config("interface se0/0/0\n bandwidth 64")

LAN_PORT = {r1: "fa0/0", r2: "g0/0", r3: "g0/0"}
LAN_XY = {r1: (60, 250), r2: (850, 100), r3: (850, 400)}
for n, r in enumerate((r1, r2, r3), 1):
    port = LAN_PORT[r]
    pc = net.pc(f"PC{n}", at=LAN_XY[r], ip=f"192.168.{n}.10/24", gateway=f"192.168.{n}.1")
    r[port].connect(pc["fa0"])
    r[port].address = f"192.168.{n}.1/24"
    nets = [f" network {sub}.0 0.0.0.255" for a, _, b, _, sub in LINKS if r in (a, b)]
    r.config(
        [
            "router eigrp 100",
            f" eigrp router-id {n}.{n}.{n}.{n}",
            " no auto-summary",
            f" network 192.168.{n}.0 0.0.0.255",
            *nets,
            f" passive-interface {r[port].name}",
        ]
    )

net.around(r1, r2, r3, shape="ellipse", outline="green", label="EIGRP AS 100", pad=50)
net.note("Se0/0/0: 64 kbit/s, feasible successor", at=(330, 360))

net.ping("PC1", "PC3", scenario="Across EIGRP")
net.ping("PC2", "PC3", scenario="Across EIGRP")
net.ping("PC3", "PC1", scenario="Back the other way")

net.save("eigrp.pkt")
print(f"eigrp.pkt: {len(net.devices)} devices, {len(net.links)} links")
