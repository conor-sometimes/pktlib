"""OSPF DR and BDR election on a shared Ethernet segment, decided by interface priority.

    uv run python examples/ccna/ospf_dr_election.py        # writes ospf_dr_election.pkt

Four routers share one switch (10.0.0.0/24, a broadcast network), so OSPF
elects a designated router (DR) and a backup (BDR) there. The highest
`ip ospf priority` wins; router ID only breaks a tie. The router IDs here
run the other way on purpose, so the result shows priority beating router ID:

  R1  priority 200, router ID 1.1.1.1  -> DR
  R2  priority 100, router ID 2.2.2.2  -> BDR
  R3  priority 1 (default), 3.3.3.3    -> DROTHER
  R4  priority 0, router ID 4.4.4.4    -> DROTHER, and can never be DR or BDR

The election isn't pre-emptive: a router that comes up later with a higher
priority doesn't take over until the DR fails. Every router in the file starts
at the same time, so the priorities decide. Each router also has its own LAN.

Check in Packet Tracer:
  - R3 `show ip ospf neighbor`: 1.1.1.1 FULL/DR, 2.2.2.2 FULL/BDR,
    4.4.4.4 2WAY/DROTHER (two DROTHERs stop at 2-WAY with each other)
  - R1 `show ip ospf interface g0/0`: State DR, Priority 200
  - R4 `show ip ospf interface g0/0`: State DROTHER, Priority 0
  - If the roles look wrong, run `clear ip ospf process` on all four (the
    election happens again with every router present)
  - PC-R4 `ping 192.168.1.10` (PC-R1): routed across the shared segment
"""

import pktlib

net = pktlib.new()

seg = net.switch("SEGMENT", at=(500, 300))
PRIORITY = {1: 200, 2: 100, 3: None, 4: 0}  # None: leave the default (1)
XY = {1: (250, 150), 2: (750, 150), 3: (250, 450), 4: (750, 450)}
for n, pri in PRIORITY.items():
    r = net.router(f"R{n}", "2911", at=XY[n])
    r["g0/0"].connect(seg[f"fa0/{n}"])
    r["g0/0"].address = f"10.0.0.{n}/24"
    if pri is not None:
        r.config(f"interface g0/0\n ip ospf priority {pri}")
    # a LAN of its own, pushed outward from the segment
    x, y = XY[n]
    pc = net.pc(f"PC-R{n}", at=(x + (-180 if x < 500 else 180), y), ip=f"192.168.{n}.10/24", gateway=f"192.168.{n}.1")
    r["g0/1"].connect(pc["fa0"])
    r["g0/1"].address = f"192.168.{n}.1/24"
    r.config(f"""
router ospf 1
 router-id {n}.{n}.{n}.{n}
 network 10.0.0.0 0.0.0.255 area 0
 network 192.168.{n}.0 0.0.0.255 area 0
 passive-interface GigabitEthernet0/1
""")

net.around(
    "R1", "R2", "R3", "R4", seg, shape="rectangle", outline="blue", label="10.0.0.0/24 shared segment, area 0", pad=40
)
net.note("R1 priority 200: DR", at=(180, 90))
net.note("R2 priority 100: BDR", at=(680, 90))
net.note("R3 priority 1: DROTHER", at=(180, 510))
net.note("R4 priority 0: never DR", at=(680, 510))

net.ping("PC-R4", "PC-R1", scenario="Across the DR segment")
net.ping("PC-R3", "PC-R2", scenario="Across the DR segment")
net.ping("PC-R1", "PC-R4", scenario="DR LAN to the priority 0 router")

net.save("ospf_dr_election.pkt")
print(f"ospf_dr_election.pkt: {len(net.devices)} devices, {len(net.links)} links")
