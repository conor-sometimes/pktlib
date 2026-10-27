"""rt03: eBGP and iBGP across five autonomous systems.

Stresses: a three-router iBGP full mesh over loopbacks (update-source,
next-hop-self) on top of OSPF in AS 65010; `aggregate-address ...
summary-only` at both ACME borders; AS-path prepending with a route-map;
iBGP between two routers of a transit AS (one is a Router-PT using its
built-in Serial2/0); eBGP multihop between loopbacks with static routes to
reach them; `default-originate` to a stub customer AS. Hardware: 2911 +
HWIC-2T, ISR4331 + NIM-2T, 2811 + WIC-2T, 2620XM + WIC-2T, 2901 + HWIC-2T,
1841+WIC-2T, Router-PT.

Check in Packet Tracer:
  - CON `show ip bgp`: 172.16.0.0/16 (only the aggregate, no /24s), best path
    via 65020 65010; the path via 65030 shows 65030 65010 65010 65010 (prepend)
  - TB `show ip bgp summary`: neighbour 100.127.0.4 (multihop) Established
  - CUST `show ip route`: `B* 0.0.0.0/0` from TB
  - ACME-3 `show ip bgp`: 198.18.0.0/24 with next hop 10.10.255.1 or .2 (next-hop-self)
  - PC-ACME3 `ping 198.18.0.10` and PC-CUST `ping 172.16.1.10`
"""

from _common import attempt, finish, pktlib, wire

net = pktlib.new()

acme1 = net.router("ACME-1", "2911", at=(300, 350))
attempt("ACME-1 HWIC-2T", acme1.add_module, "HWIC-2T")
acme2 = net.router("ACME-2", "ISR4331", at=(300, 600))
attempt("ACME-2 NIM-2T", acme2.add_module, "NIM-2T")
acme3 = net.router("ACME-3", "1941", at=(100, 475))
ta1 = net.router("TA-1", "2811", at=(600, 250))
attempt("TA-1 WIC-2T", ta1.add_module, "WIC-2T")
ta2 = net.router("TA-2", "Router-PT", at=(900, 250))
tb = net.router("TB", "2620XM", at=(600, 650))
attempt("TB WIC-2T", tb.add_module, "WIC-2T")
con = net.router("CON", "2901", at=(1150, 450))
attempt("CON HWIC-2T", con.add_module, "HWIC-2T")
cust = net.router("CUST", "1841+WIC-2T", at=(900, 800))

# --- AS 65010: OSPF underlay, iBGP full mesh on loopbacks --------------------
LO = {acme1: "10.10.255.1", acme2: "10.10.255.2", acme3: "10.10.255.3"}
attempt("ACME-1/ACME-2", wire, acme1, "g0/1", acme2, "g0/0/1", "10.10.0.0/30")
attempt("ACME-1/ACME-3", wire, acme1, "g0/2", acme3, "g0/1", "10.10.0.4/30")
attempt("ACME-2/ACME-3", wire, acme2, "g0/0/2", acme3, "g0/0", "10.10.0.8/30")
for r, lo in LO.items():
    r.config(
        f"interface loopback 0\n ip address {lo} 255.255.255.255\n"
        f"router ospf 1\n router-id {lo}\n network 10.10.0.0 0.0.255.255 area 0"
    )
    r.config(
        f"router bgp 65010\n bgp router-id {lo}\n"
        + "".join(
            f" neighbor {peer} remote-as 65010\n neighbor {peer} update-source Loopback0\n"
            f" neighbor {peer} next-hop-self\n"
            for o, peer in LO.items()
            if o is not r
        )
    )

# ACME-3's LAN; ACME-1's LAN
# the 1941 has two gig ports, both used for the mesh: add a 4-port switch card for the LAN
attempt("ACME-3 HWIC-4ESW", acme3.add_module, "HWIC-4ESW")
pc3 = net.pc("PC-ACME3", at=(100, 650), ip="172.16.1.10/24", gateway="172.16.1.1")
# HWIC-4ESW ports are switch ports: the gateway is an SVI
attempt("ACME-3 fa0/0/0 to PC", lambda: acme3["fa0/0/0"].connect(pc3["fa0"]))
acme3.config("""
interface Vlan1
 ip address 172.16.1.1 255.255.255.0
 no shutdown
router bgp 65010
 network 172.16.1.0 mask 255.255.255.0
""")
pc1 = net.pc("PC-ACME1", at=(300, 200), ip="172.16.2.10/24", gateway="172.16.2.1")
acme1["g0/0"].connect(pc1["fa0"])
acme1["g0/0"].address = "172.16.2.1/24"
acme1.config("router bgp 65010\n network 172.16.2.0 mask 255.255.255.0")

# --- eBGP out of AS 65010 --------------------------------------------------
attempt("ACME-1/TA-1 serial", wire, acme1, "se0/0/0", ta1, "se0/0/0", "100.64.1.0/30")
attempt("ACME-2/TB serial", wire, acme2, "se0/1/0", tb, "se0/0", "100.64.2.0/30")
acme1.config("""
router bgp 65010
 neighbor 100.64.1.2 remote-as 65020
 aggregate-address 172.16.0.0 255.255.0.0 summary-only
""")
acme2.config("""
route-map PREPEND permit 10
 set as-path prepend 65010 65010
router bgp 65010
 neighbor 100.64.2.2 remote-as 65030
 neighbor 100.64.2.2 route-map PREPEND out
 aggregate-address 172.16.0.0 255.255.0.0 summary-only
""")

# --- AS 65020: two routers, iBGP between them ------------------------------
attempt("TA-1/TA-2 ethernet", wire, ta1, "fa0/0", ta2, "fa0/0", "100.65.0.0/30")
attempt("TA-2 Serial2/0 to CON", wire, ta2, "se2/0", con, "se0/0/0", "100.66.1.0/30")
ta1.config("""
router bgp 65020
 bgp router-id 100.65.0.1
 neighbor 100.64.1.1 remote-as 65010
 neighbor 100.65.0.2 remote-as 65020
 neighbor 100.65.0.2 next-hop-self
""")
ta2.config("""
router bgp 65020
 bgp router-id 100.65.0.2
 neighbor 100.65.0.1 remote-as 65020
 neighbor 100.65.0.1 next-hop-self
 neighbor 100.66.1.2 remote-as 65040
""")

# --- AS 65030 to AS 65040: eBGP multihop between loopbacks ------------------
attempt("TB/CON ethernet", wire, tb, "fa0/0", con, "g0/1", "100.66.2.0/30")
tb.config("""
interface loopback 0
 ip address 100.127.0.3 255.255.255.255
ip route 100.127.0.4 255.255.255.255 100.66.2.2
router bgp 65030
 bgp router-id 100.127.0.3
 neighbor 100.64.2.1 remote-as 65010
 neighbor 100.127.0.4 remote-as 65040
 neighbor 100.127.0.4 ebgp-multihop 2
 neighbor 100.127.0.4 update-source Loopback0
""")
con.config("""
interface loopback 0
 ip address 100.127.0.4 255.255.255.255
ip route 100.127.0.3 255.255.255.255 100.66.2.1
router bgp 65040
 bgp router-id 100.127.0.4
 neighbor 100.66.1.1 remote-as 65020
 neighbor 100.127.0.3 remote-as 65030
 neighbor 100.127.0.3 ebgp-multihop 2
 neighbor 100.127.0.3 update-source Loopback0
 network 198.18.0.0 mask 255.255.255.0
""")
srv = net.server("CONTENT", at=(1350, 450), ip="198.18.0.10/24", gateway="198.18.0.1")
con["g0/0"].connect(srv["fa0"])
con["g0/0"].address = "198.18.0.1/24"

# --- AS 65050: stub customer, default only ----------------------------------
attempt("TB/CUST serial", wire, tb, "se0/1", cust, "se0/0/0", "100.67.0.0/30")
tb.config("router bgp 65030\n neighbor 100.67.0.2 remote-as 65050\n neighbor 100.67.0.2 default-originate")
cust.config(
    "router bgp 65050\n bgp router-id 100.67.0.2\n neighbor 100.67.0.1 remote-as 65030\n"
    " network 203.0.113.0 mask 255.255.255.0"
)
pcc = net.pc("PC-CUST", at=(1100, 800), ip="203.0.113.10/24", gateway="203.0.113.1")
cust["fa0/0"].connect(pcc["fa0"])
cust["fa0/0"].address = "203.0.113.1/24"

# The audit reads interface addresses: does it see ACME-3's SVI gateway?
print("ACME-3 interfaces:", {k: v for k, v in acme3.interfaces.items() if v[0]})

net.around(acme1, acme2, acme3, pc1, pc3, shape="rectangle", outline="blue", label="AS 65010 (iBGP mesh + OSPF)")
net.around(ta1, ta2, shape="ellipse", outline="green", label="AS 65020")
net.around(tb, shape="ellipse", outline="orange", label="AS 65030")
net.around(con, srv, shape="ellipse", outline="red", label="AS 65040")
net.around(cust, pcc, shape="ellipse", outline="grey", label="AS 65050 stub")
finish(net, "rt03_bgp_ases")
