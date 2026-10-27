"""Four routing domains, OSPF, EIGRP, RIP and static, joined by one router that redistributes between them all.

    uv run python examples/showcase/redistribution.py       # writes redistribution.pkt

border     a 2911 with two HWIC-2T cards, in every domain at once. Each
           protocol takes in the other two and the static route; with one
           redistribution point, no route can loop back.
ospf       OSPF-A and OSPF-B in area 0, OSPF-C behind OSPF-B in area 1;
           the data centre server sits on OSPF-A (10.1.0.0/16)
eigrp      EIGRP-A and EIGRP-B, AS 100 (10.2.0.0/16)
rip        RIP-A and RIP-B, version 2 on serial links (172.16.0.0/16).
           RIP-B also has a LAB LAN, 172.31.0.0/24, that it never advertises:
           nobody outside can reach it
static     STUB, a branch with no routing protocol: a default route out,
           and a static route to its LAN on BORDER (10.4.0.0/24)

Check in Packet Tracer:
  BORDER# show ip route                -> O, O IA, D, R and S routes side by side
  OSPF-C# show ip route                -> O E2 for 10.2.x, 172.16.x and 10.4.0.0
  EIGRP-B# show ip route               -> D EX for the OSPF, RIP and static networks
  RIP-B# show ip route                 -> R for everything else, metric 4 and up
  RIP-PC ping 10.1.1.10 (DC-SERVER)    -> RIP to OSPF
  STUB-PC ping 10.2.2.10 (EIGRP-PC)    -> static to EIGRP
  DC-SERVER ping 172.31.0.10 (LAB-PC)  -> fails: the lab is never advertised
  Or click the ping scenarios under the workspace.
"""

import pktlib

EIGRP_METRIC = "1544 2000 255 1 1500"  # bandwidth, delay, reliability, load, MTU
RIP_METRIC = 3  # hops

net = pktlib.new()


def link(a, ap: str, b, bp: str, net30: str) -> None:
    """Cable a.ap to b.bp and give them .1 and .2 of a /30 like '10.1.255.4' (a is the DCE on serial)."""
    a[ap].connect(b[bp])
    base, last = net30.rsplit(".", 1)
    a[ap].address = f"{base}.{int(last) + 1}/30"
    b[bp].address = f"{base}.{int(last) + 2}/30"


def lan(router, port: str, net24: str, name: str, at: tuple[int, int], kind: str = "pc"):
    """A host on the router's LAN port, like '10.1.1': router .1, host .10."""
    router[port].address = f"{net24}.1/24"
    make = net.server if kind == "server" else net.pc
    host = make(name, at=at, ip=f"{net24}.10/24", gateway=f"{net24}.1")
    router[port].connect(host["fa0"])
    return host


# --- the border ---------------------------------------------------------------
border = net.router("BORDER", "2911", at=(800, 380))
border.add_module("HWIC-2T", slot=(0, 0))  # Serial0/0/0 and 0/0/1

# --- OSPF: area 0 and area 1 ----------------------------------------------------
ospf_a = net.router("OSPF-A", "2911", at=(450, 230))
ospf_b = net.router("OSPF-B", "2911", at=(450, 60))
ospf_c = net.router("OSPF-C", "1841", at=(800, 60))
link(border, "g0/0", ospf_a, "g0/0", "10.1.255.0")
link(ospf_a, "g0/1", ospf_b, "g0/0", "10.1.255.4")
link(ospf_b, "g0/1", ospf_c, "fa0/0", "10.1.255.8")
dc = lan(ospf_a, "g0/2", "10.1.1", "DC-SERVER", at=(200, 230), kind="server")
ospf_pc = lan(ospf_c, "fa0/1", "10.1.3", "OSPF-PC", at=(1050, 60))
ospf_a.config("""
router ospf 1
 router-id 10.1.254.1
 network 10.1.255.0 0.0.0.7 area 0
 network 10.1.1.0 0.0.0.255 area 0
""")
ospf_b.config("""
router ospf 1
 router-id 10.1.254.2
 network 10.1.255.4 0.0.0.3 area 0
 network 10.1.255.8 0.0.0.3 area 1
""")
ospf_c.config("""
router ospf 1
 router-id 10.1.254.3
 network 10.1.255.8 0.0.0.3 area 1
 network 10.1.3.0 0.0.0.255 area 1
""")

# --- EIGRP 100 ------------------------------------------------------------------
eigrp_a = net.router("EIGRP-A", "2911", at=(1250, 380))
eigrp_b = net.router("EIGRP-B", "2911", at=(1550, 380))
link(border, "g0/1", eigrp_a, "g0/0", "10.2.255.0")
link(eigrp_a, "g0/1", eigrp_b, "g0/0", "10.2.255.4")
eigrp_pc = lan(eigrp_b, "g0/1", "10.2.2", "EIGRP-PC", at=(1800, 380))
eigrp_a.config("router eigrp 100\n no auto-summary\n network 10.2.255.0 0.0.0.7")
eigrp_b.config("router eigrp 100\n no auto-summary\n network 10.2.255.4 0.0.0.3\n network 10.2.2.0 0.0.0.255")

# --- RIP version 2 ----------------------------------------------------------------
rip_a = net.router("RIP-A", "1841+WIC-2T", at=(450, 560))
rip_b = net.router("RIP-B", "1841+WIC-2T", at=(450, 740))
link(border, "se0/0/0", rip_a, "se0/0/0", "172.16.255.0")
link(rip_a, "se0/0/1", rip_b, "se0/0/0", "172.16.255.4")
rip_a_pc = lan(rip_a, "fa0/0", "172.16.1", "RIP-PC", at=(200, 560))
rip_b_pc = lan(rip_b, "fa0/0", "172.16.2", "RIP-PC2", at=(200, 740))
lab_pc = lan(rip_b, "fa0/1", "172.31.0", "LAB-PC", at=(700, 740))  # outside 172.16: never advertised
for r in (rip_a, rip_b):
    r.config("router rip\n version 2\n no auto-summary\n network 172.16.0.0")

# --- static: a branch with no routing protocol --------------------------------------
stub = net.router("STUB", "1841+WIC-2T", at=(1150, 600))
link(border, "se0/0/1", stub, "se0/0/0", "10.4.255.0")
stub_pc = lan(stub, "fa0/0", "10.4.0", "STUB-PC", at=(1400, 600))
stub.config("ip route 0.0.0.0 0.0.0.0 10.4.255.1")

# --- BORDER: every protocol takes in the others ---------------------------------------
border.config(f"""
ip route 10.4.0.0 255.255.255.0 10.4.255.2
router ospf 1
 router-id 10.255.255.1
 network 10.1.255.0 0.0.0.3 area 0
 redistribute eigrp 100 subnets
 redistribute rip subnets
 redistribute static subnets
router eigrp 100
 no auto-summary
 network 10.2.255.0 0.0.0.3
 redistribute ospf 1 metric {EIGRP_METRIC}
 redistribute rip metric {EIGRP_METRIC}
 redistribute static metric {EIGRP_METRIC}
router rip
 version 2
 no auto-summary
 network 172.16.0.0
 redistribute ospf 1 metric {RIP_METRIC}
 redistribute eigrp 100 metric {RIP_METRIC}
 redistribute static metric {RIP_METRIC}
""")

# --- drawings -------------------------------------------------------------------------
net.around(ospf_a, ospf_b, ospf_c, dc, ospf_pc, shape="ellipse", outline="blue", label="OSPF 1: area 0 and 1", pad=40)
net.around(eigrp_a, eigrp_b, eigrp_pc, shape="ellipse", outline="green", label="EIGRP 100", pad=40)
net.around(rip_a, rip_b, rip_a_pc, rip_b_pc, lab_pc, shape="ellipse", outline="orange", label="RIP v2", pad=40)
net.around(stub, stub_pc, shape="ellipse", outline="grey", label="STATIC", pad=40)
net.around(border, shape="ellipse", outline="red", label="BORDER: redistributes everything", pad=40)

# --- ping checks ------------------------------------------------------------------------
net.ping("RIP-PC", "DC-SERVER", scenario="Every domain to the data centre")
net.ping("EIGRP-PC", "DC-SERVER", scenario="Every domain to the data centre")
net.ping("STUB-PC", "DC-SERVER", scenario="Every domain to the data centre")
net.ping("OSPF-PC", "DC-SERVER", scenario="Every domain to the data centre")
net.ping("OSPF-PC", "EIGRP-PC", scenario="Across the border")
net.ping("EIGRP-PC", "RIP-PC2", scenario="Across the border")
net.ping("RIP-PC2", "STUB-PC", scenario="Across the border")
net.ping("STUB-PC", "OSPF-PC", scenario="Across the border")
net.ping("DC-SERVER", "LAB-PC", scenario="To the unadvertised lab: should FAIL")
net.ping("EIGRP-PC", "LAB-PC", scenario="To the unadvertised lab: should FAIL")

net.save("redistribution.pkt")
print(f"redistribution.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
