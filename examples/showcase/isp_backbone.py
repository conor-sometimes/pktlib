"""An ISP backbone: four POPs in an OSPF ring, a BGP border to the internet, and customer sites.

    uv run python examples/showcase/isp_backbone.py         # writes isp_backbone.pkt

backbone   four POP routers (2911, each with an HWIC-2T for serial
           customers) in a gigabit ring, OSPF area 0 on loopbacks and links
border     an ISR4331 peering over eBGP (AS 65000 to AS 65001) with a
           transit provider; it announces the ISP's three blocks (each
           nailed to null0, as on a real border), and puts a default into OSPF
customers  each POP routes its customers' blocks with a static route and
           redistributes it into OSPF, so every POP and the border learn them
             ACME    one site on serial, servers on public addresses
             BETA    two sites, at two POPs, reaching each other over the backbone
             CAFE    a small shop on ethernet, private LAN, NAT overload
                     onto the address the ISP gave its router

Addresses: backbone links 10.0.0.0/24 in /30s, loopbacks 10.255.255.n,
customer WAN links 100.64.n.0/30, customer LANs from 198.51.100.0/24 and
203.0.113.0/24.

Check in Packet Tracer:
  BORDER# show ip bgp summary          -> 100.127.0.1 (TRANSIT) up, prefixes received
  TRANSIT# show ip route bgp           -> 198.51.100.0/24, 203.0.113.0/24, 100.64.0.0/16
  DUBLIN# show ip ospf neighbor        -> GALWAY, BELFAST and BORDER FULL
  CORK# show ip route ospf             -> O E2 routes for every customer LAN, O*E2 default
  CAFE# show ip nat translations       -> after CAFE-TILL pings 8.8.8.8, entries on 100.64.4.2
  ACME-PC ping 8.8.8.8                 -> success
  BETA-HQ-PC ping 203.0.113.20 (BETA-BRANCH-PC) -> across the ring
  Or click the ping scenarios under the workspace.
"""

import pktlib

net = pktlib.new()

# --- backbone: four POPs in a ring -------------------------------------------
POPS = {"DUBLIN": (900, 280), "BELFAST": (1250, 440), "CORK": (900, 600), "GALWAY": (550, 440)}
pops = {}
for n, (name, xy) in enumerate(POPS.items(), 1):
    r = net.router(name, "2911", at=xy)
    r.add_module("HWIC-2T", slot=(0, 0))
    r.config(f"""
interface loopback 0
 ip address 10.255.255.{n} 255.255.255.255
router ospf 1
 router-id 10.255.255.{n}
 network 10.255.255.{n} 0.0.0.0 area 0
 redistribute static subnets
""")
    pops[name] = r

ring = list(pops.values())
for i, a in enumerate(ring):
    b = ring[(i + 1) % len(ring)]
    a["g0/0"].connect(b["g0/1"])
    a["g0/0"].address = f"10.0.0.{4 * i + 1}/30"
    b["g0/1"].address = f"10.0.0.{4 * i + 2}/30"
    for r in (a, b):
        r.config(f"router ospf 1\n network 10.0.0.{4 * i} 0.0.0.3 area 0")

# --- border and transit -------------------------------------------------------
BLOCKS = ["198.51.100.0 255.255.255.0", "203.0.113.0 255.255.255.0", "100.64.0.0 255.255.0.0"]
border = net.router("BORDER", "ISR4331", at=(900, 150))
border["g0/0/0"].connect(pops["DUBLIN"]["g0/2"])
border["g0/0/0"].address = "10.0.0.17/30"
pops["DUBLIN"]["g0/2"].address = "10.0.0.18/30"
pops["DUBLIN"].config("router ospf 1\n network 10.0.0.16 0.0.0.3 area 0")

transit = net.router("TRANSIT", "2911", at=(900, 30))
inet = net.server("INTERNET", at=(1150, 30), ip="8.8.8.8/24", gateway="8.8.8.1")
transit["g0/1"].connect(inet["fa0"])
transit["g0/1"].address = "8.8.8.1/24"
transit["g0/0"].connect(border["g0/0/1"])
transit["g0/0"].address = "100.127.0.1/30"
border["g0/0/1"].address = "100.127.0.2/30"
transit.config("""
router bgp 65001
 neighbor 100.127.0.2 remote-as 65000
 network 8.8.8.0 mask 255.255.255.0
""")
border.config(
    "\n".join(f"ip route {b} null0" for b in BLOCKS)
    + """
ip route 0.0.0.0 0.0.0.0 100.127.0.1
router bgp 65000
 neighbor 100.127.0.1 remote-as 65001
"""
    + "\n".join(f" network {b.replace(' ', ' mask ')}" for b in BLOCKS)
    + """
router ospf 1
 router-id 10.255.255.100
 network 10.0.0.16 0.0.0.3 area 0
 default-information originate
"""
)


# --- customers ----------------------------------------------------------------
def customer(pop: str, pop_port: str, name: str, model: str, wan: int, lan: str, at: tuple[int, int]):
    """A customer router on 100.64.<wan>.0/30, the POP's static route to its LAN."""
    ce = net.router(name, model, at=at)
    ce_port = "se0/0/0" if pop_port.startswith("se") else "g0/0"
    pops[pop][pop_port].connect(ce[ce_port])  # on serial, the POP is the DCE end
    pops[pop][pop_port].address = f"100.64.{wan}.1/30"
    ce[ce_port].address = f"100.64.{wan}.2/30"
    ce.config(f"ip route 0.0.0.0 0.0.0.0 100.64.{wan}.1")
    network, mask = lan.split()
    pops[pop].config(f"ip route {network} {mask} 100.64.{wan}.2\nrouter ospf 1\n network 100.64.{wan}.0 0.0.0.3 area 0")
    return ce


def lan_hosts(router, port: str, hosts: list[tuple[str, str, str]], at: tuple[int, int], gw: str):
    """A switch on the router's LAN port and hosts on it: (name, kind, address/len or '')."""
    sw = net.switch(f"{router.name}-SW", at=at)
    router[port].connect(sw["g0/1"])
    out = [router, sw]
    for i, (hname, kind, ip) in enumerate(hosts):
        make = {"pc": net.pc, "server": net.server, "laptop": net.laptop}[kind]
        d = make(hname, at=(at[0] - 90 + 90 * i, at[1] + 120))
        if ip:
            d.set_ip(ip, gw)
        else:
            d.use_dhcp()
        sw[f"fa0/{i + 1}"].connect(d["fa0"])
        out.append(d)
    return out


# ACME: public servers behind a serial line at DUBLIN
acme = customer("DUBLIN", "se0/0/0", "ACME", "1841+WIC-2T", 1, "198.51.100.0 255.255.255.240", at=(380, 150))
acme["fa0/0"].address = "198.51.100.1/28"
acme_site = lan_hosts(
    acme,
    "fa0/0",
    [("ACME-WEB", "server", "198.51.100.10/28"), ("ACME-PC", "pc", "198.51.100.11/28")],
    at=(180, 150),
    gw="198.51.100.1",
)

# BETA: head office at CORK, branch at GALWAY
beta_hq = customer("CORK", "se0/0/0", "BETA-HQ", "1841+WIC-2T", 2, "203.0.113.0 255.255.255.240", at=(900, 820))
beta_hq["fa0/0"].address = "203.0.113.1/28"
beta_hq_site = lan_hosts(
    beta_hq,
    "fa0/0",
    [("BETA-FILES", "server", "203.0.113.10/28"), ("BETA-HQ-PC", "pc", "203.0.113.11/28")],
    at=(1080, 820),
    gw="203.0.113.1",
)
beta_br = customer("GALWAY", "se0/0/0", "BETA-BRANCH", "1841+WIC-2T", 3, "203.0.113.16 255.255.255.240", at=(150, 440))
beta_br["fa0/0"].address = "203.0.113.17/28"
beta_br_site = lan_hosts(
    beta_br, "fa0/0", [("BETA-BRANCH-PC", "pc", "203.0.113.20/28")], at=(150, 580), gw="203.0.113.17"
)

# CAFE: ethernet at BELFAST, a private LAN, NAT overload onto its WAN address.
# Its LAN is never routed by the ISP, so the static route is for its WAN /30 only.
cafe = net.router("CAFE", "1941", at=(1750, 440))
pops["BELFAST"]["g0/2"].connect(cafe["g0/0"])
pops["BELFAST"]["g0/2"].address = "100.64.4.1/30"
pops["BELFAST"].config("router ospf 1\n network 100.64.4.0 0.0.0.3 area 0")
cafe["g0/0"].address = "100.64.4.2/30"
cafe["g0/1"].address = "192.168.1.1/24"
cafe.config("""
interface g0/0
 ip nat outside
interface g0/1
 ip nat inside
ip dhcp excluded-address 192.168.1.1 192.168.1.9
ip dhcp pool CAFE
 network 192.168.1.0 255.255.255.0
 default-router 192.168.1.1
 dns-server 8.8.8.8
access-list 1 permit 192.168.1.0 0.0.0.255
ip nat inside source list 1 interface GigabitEthernet0/0 overload
ip route 0.0.0.0 0.0.0.0 100.64.4.1
""")
cafe_site = lan_hosts(
    cafe,
    "g0/1",
    [("CAFE-TILL", "pc", "192.168.1.10/24"), ("CAFE-LAPTOP", "laptop", "")],
    at=(1750, 580),
    gw="192.168.1.1",
)

# --- drawings -------------------------------------------------------------------
net.around(*pops.values(), shape="ellipse", outline="blue", pad=30)
net.note("BACKBONE AS 65000\nOSPF area 0", at=(840, 430))  # in the middle of the ring
net.around(transit, inet, shape="rectangle", outline="grey", label="TRANSIT AS 65001", pad=40)
net.around(*acme_site, shape="rectangle", outline="green", label="ACME (static, public LAN)", pad=35)
net.around(*beta_hq_site, shape="rectangle", outline="orange", label="BETA head office", pad=35)
net.around(*beta_br_site, shape="rectangle", outline="orange", label="BETA branch", pad=35)
net.around(*cafe_site, shape="rectangle", outline="purple", label="CAFE (NAT overload)", pad=35)
net.note("Customer blocks: 198.51.100.0/24, 203.0.113.0/24.\nWAN links: 100.64.<n>.0/30.", at=(1350, 120))

# --- ping checks --------------------------------------------------------------
net.ping("ACME-PC", "INTERNET", scenario="Customers to internet")
net.ping("BETA-HQ-PC", "INTERNET", scenario="Customers to internet")
net.ping("BETA-BRANCH-PC", "INTERNET", scenario="Customers to internet")
net.ping("CAFE-TILL", "INTERNET", scenario="Customers to internet")
net.ping("INTERNET", "ACME-WEB", scenario="Internet to ACME web server")
net.ping("BETA-HQ-PC", "BETA-BRANCH-PC", scenario="BETA site to site")
net.ping("BETA-BRANCH-PC", "BETA-FILES", scenario="BETA site to site")
net.ping("ACME-PC", "BETA-FILES", scenario="Customer to customer")
net.ping("INTERNET", "CAFE-TILL", scenario="Internet to cafe private LAN: should FAIL")

net.save("isp_backbone.pkt")
print(f"isp_backbone.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
