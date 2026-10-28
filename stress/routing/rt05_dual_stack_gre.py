"""rt05: dual stack, OSPFv3 and EIGRP for IPv6 redistributed, GRE tunnel.

Stresses: `ipv6 unicast-routing` plus `ipv6 address` (global and a manual
link-local) on every routed interface; OSPFv2 + OSPFv3 in one domain and
EIGRP + EIGRP for IPv6 (`ipv6 router eigrp 200`, `no shutdown` inside it) in
the other, with V6-B redistributing both families both ways; a GRE tunnel between V6-C
and V6-E carrying IPv4 and IPv6 static routes to loopbacks nothing else
advertises; PCs given IPv6 addresses (pktlib has no call for it: see
FINDINGS printed by the script). Packet Tracer 8.2 dropped two lines this
used to write (checks 18 and 19, 26 Oct 2026), so they're gone and refused()
flags them: `default-information originate always` under `ipv6 router ospf`,
and `include-connected` on V6-B's IPv6 EIGRP redistribution.
Hardware: 2911, ISR4331 + NIM-2T, 1841+WIC-2T, 2811 + WIC-2T, 1941 + HWIC-2T.

Check in Packet Tracer:
  - V6-B `show ipv6 route`: O, D and (on the far side) OE2 / EX routes
  - V6-A `show ipv6 ospf neighbor`, V6-E `show ipv6 eigrp neighbors`
  - V6-C `show interface tunnel0`: up/up; `ping 192.168.55.1 source 192.168.33.1`
    and `ping 2001:db8:55::1 source 2001:db8:33::1` (both only via the tunnel)
  - V6-A `ping 2001:db8:5:5::1` (V6-E's LAN, across the redistribution)
  - V6-B `show running-config`: does `ipv6 unicast-routing` sit above the
    interfaces? pktlib writes it near `end`; if PT replays in order, the
    `ipv6 ospf` / `ipv6 eigrp` interface lines may have been refused
"""

from _common import attempt, finish, host, note, pktlib, plain, wire

net = pktlib.new()

a = net.router("V6-A", "2911", at=(200, 300))
b = net.router("V6-B", "ISR4331", at=(550, 300))
attempt("V6-B NIM-2T", b.add_module, "NIM-2T")
c = net.router("V6-C", "1841+WIC-2T", at=(400, 550))
d = net.router("V6-D", "2811", at=(850, 150))
attempt("V6-D WIC-2T", d.add_module, "WIC-2T")
e = net.router("V6-E", "1941", at=(850, 500))
attempt("V6-E HWIC-2T", e.add_module, "HWIC-2T")

for r in (a, b, c, d, e):
    r.config("ipv6 unicast-routing")

LINKS = [  # (dce, port, dte, port, n, family-domain)
    (a, "g0/1", b, "g0/0/1", 1, "ospf"),
    (a, "g0/2", c, "fa0/1", 2, "ospf"),
    (b, "se0/1/0", c, "se0/0/0", 3, "ospf"),
    (b, "se0/1/1", d, "se0/0/0", 4, "eigrp"),
    (d, "se0/0/1", e, "se0/0/0", 5, "eigrp"),
    (b, "g0/0/2", e, "g0/1", 6, "eigrp"),
]
RID = {a: "6.6.6.1", b: "6.6.6.2", c: "6.6.6.3", d: "6.6.6.4", e: "6.6.6.5"}


def v6(r, port, prefix, me, domain):
    """Global address, a manual link-local and the routing protocol on one interface."""
    name = r[port].name
    lines = [
        f"interface {name}",
        f" ipv6 address {prefix}{me}/64",
        f" ipv6 address fe80::{RID[r].split('.')[-1]} link-local",
    ]
    lines.append(" ipv6 ospf 1 area 0" if domain == "ospf" else " ipv6 eigrp 200")
    r.config(lines)


for x, xp, y, yp, n, domain in LINKS:
    cidr = f"10.6.0.{4 * (n - 1)}/30"
    attempt(f"{x.name}-{y.name}", wire, x, xp, y, yp, cidr)
    v6(x, xp, f"2001:db8:6:{n}::", 1, domain)
    v6(y, yp, f"2001:db8:6:{n}::", 2, domain)
    for r in (x, y):
        if domain == "ospf":
            r.config(f"router ospf 1\n network 10.6.0.{4 * (n - 1)} 0.0.0.3 area 0")
        else:
            r.config(f"router eigrp 200\n no auto-summary\n network 10.6.0.{4 * (n - 1)} 0.0.0.3")

LANS = {a: ("g0/0", 1, "ospf"), c: ("fa0/0", 3, "ospf"), d: ("fa0/0", 4, "eigrp"), e: ("g0/0", 5, "eigrp")}
for r, (port, n, domain) in LANS.items():
    cidr = f"192.168.{n}.0/24"
    r[port].address = host(cidr, 1)
    v6(r, port, f"2001:db8:{n}:{n}::", 1, domain)
    if domain == "ospf":
        r.config(f"router ospf 1\n network 192.168.{n}.0 0.0.0.255 area 0")
    else:
        r.config(f"router eigrp 200\n network 192.168.{n}.0 0.0.0.255")
    x, y = r.xy
    pc = net.pc(f"PC-{r.name}", at=(x, y + 120), ip=host(cidr, 10), gateway=plain(cidr, 1))
    r[port].connect(pc["fa0"])
    # the natural ways to give a PC an IPv6 address; pktlib's are IPv4 only
    attempt(
        f"PC-{r.name} set_ip IPv6", pc.set_ip, f"2001:db8:{n}:{n}::10", 64, f"2001:db8:{n}:{n}::1", port="FastEthernet0"
    )
    attempt(f"PC-{r.name}.address = IPv6", setattr, pc["fa0"], "address", f"2001:db8:{n}:{n}::10/64")
note(
    "no API for an end device's IPv6 address, gateway or SLAAC/DHCPv6 mode; PCs here are IPv4 only, "
    "so IPv6 can only be pinged router to router"
)

for r, rid in RID.items():
    r.config(f"router ospf 1\n router-id {rid}" if r in (a, b, c) else f"router eigrp 200\n eigrp router-id {rid}")
for r in (a, b, c):
    r.config(f"ipv6 router ospf 1\n router-id {RID[r]}")
for r in (b, d, e):
    r.config(f"ipv6 router eigrp 200\n eigrp router-id {RID[r]}\n no shutdown")

# V6-A: an IPv6 "internet" loopback
a.config("""
interface loopback 0
 ipv6 address 2001:db8:ffff::1/128
 ipv6 ospf 1 area 0
""")

# V6-B: both families, both ways
b.config("""
router ospf 1
 redistribute eigrp 200 subnets
router eigrp 200
 redistribute ospf 1 metric 1544 20000 255 1 1500
ipv6 router ospf 1
 redistribute eigrp 200
ipv6 router eigrp 200
 redistribute ospf 1 metric 1544 20000 255 1 1500
""")

# GRE between V6-C and V6-E, carrying routes nothing else knows
c.config("""
interface loopback 33
 ip address 192.168.33.1 255.255.255.0
 ipv6 address 2001:db8:33::1/64
interface Tunnel0
 ip address 172.31.0.1 255.255.255.252
 ipv6 address 2001:db8:31::1/64
 tunnel source Serial0/0/0
 tunnel destination 10.6.0.18
 tunnel mode gre ip
ip route 192.168.55.0 255.255.255.0 172.31.0.2
ipv6 route 2001:db8:55::/64 2001:db8:31::2
""")
e.config("""
interface loopback 55
 ip address 192.168.55.1 255.255.255.0
 ipv6 address 2001:db8:55::1/64
interface Tunnel0
 ip address 172.31.0.2 255.255.255.252
 ipv6 address 2001:db8:31::2/64
 tunnel source Serial0/0/0
 tunnel destination 10.6.0.10
 tunnel mode gre ip
ip route 192.168.33.0 255.255.255.0 172.31.0.1
ipv6 route 2001:db8:33::/64 2001:db8:31::1
""")

# Where did `ipv6 unicast-routing` land relative to the interface lines that need it?
cfg = b.running_config
first_v6_if = next(i for i, l in enumerate(cfg) if l.strip().startswith("ipv6 ospf") or l.strip() == "ipv6 eigrp 200")
uni = cfg.index("ipv6 unicast-routing")
print(f"V6-B: first `ipv6 ospf/eigrp` interface line at {first_v6_if}, `ipv6 unicast-routing` at {uni}")
if uni > first_v6_if:
    note(
        "`ipv6 unicast-routing` is written after interface blocks that use `ipv6 ospf`/`ipv6 eigrp` "
        "(merge_config puts new top-level lines before `end`); IOS refuses those interface lines "
        "until unicast-routing is on, so PT may drop them on replay"
    )
print("V6-B Gig0/0/1 as pktlib reads it:", b.interface_config("GigabitEthernet0/0/1"))
print("V6-A Loopback0 address as pktlib reads it:", a.interfaces.get("Loopback0"))

net.around(a, c, "PC-V6-A", "PC-V6-C", shape="ellipse", outline="blue", label="OSPFv2 + OSPFv3")
net.around(d, e, "PC-V6-D", "PC-V6-E", shape="ellipse", outline="green", label="EIGRP 200 v4 + v6")
finish(net, "rt05_dual_stack_gre")
