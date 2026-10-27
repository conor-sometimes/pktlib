"""A dual-homed enterprise: two ISPs, an HQ campus, two branches over serial WAN.

  uv run python examples/showcase/enterprise.py            # writes enterprise.pkt

internet   ISP1 (AS 65001) and ISP2 (AS 65002) peer over eBGP; a DNS
           server on 8.8.8.8 behind ISP1, a web server on 1.1.1.1 behind ISP2
hq edge    EDGE1 (ISR4331, to ISP1) and EDGE2 (2911, to ISP2), AS 65100.
           Each announces its half of 192.0.2.0/24 over eBGP and NATs HQ
           onto it; EDGE1 also maps the public web server to 192.0.2.80.
           EDGE1 originates the default into OSPF; the cores keep a
           floating static default via EDGE2 in case EDGE1 goes.
hq campus  two 3650 cores: an LACP channel between them, rapid PVST, HSRP
           gateways, OSPF area 0, DHCP; two 2960 access switches; a guest
           VLAN an ACL keeps out of everything internal
branch 1   1841 with a WIC-2T fitted, serial to EDGE1, OSPF area 1 (EDGE1 is
           the ABR), router-on-a-stick, DHCP on the router
branch 2   2911 with an HWIC-2T fitted, serial to EDGE1, EIGRP 100,
           redistributed both ways with OSPF on EDGE1; a PoE 3560, IP
           phones registering with a CME router, a PC behind each phone
"""

import ipaddress

import pktlib

net = pktlib.new()


def nw(cidr: str) -> ipaddress.IPv4Network:
    return ipaddress.IPv4Network(cidr)


def at(cidr: str, n: int) -> str:
    """The n-th address of a network, '/len' on the end: at('10.0.0.0/30', 1) -> '10.0.0.1/30'."""
    n_ = nw(cidr)
    return f"{n_.network_address + n}/{n_.prefixlen}"


def wild(cidr: str) -> str:
    n_ = nw(cidr)
    return f"{n_.network_address} {n_.hostmask}"


def plain(cidr: str, n: int) -> str:
    return str(nw(cidr).network_address + n)


# --- internet ---------------------------------------------------------------
ISP_PEER, ISP1_HQ, ISP2_HQ = "100.64.0.0/30", "203.0.113.0/30", "198.51.100.0/30"
DNS_NET, WEB_NET = "8.8.8.0/24", "1.1.1.0/24"
PUBLIC = "192.0.2.0/24"
EDGE1_POOL, EDGE2_POOL = "192.0.2.0/25", "192.0.2.128/25"

isp1 = net.router("ISP1", "2911", at=(500, 60))
isp2 = net.router("ISP2", "2911", at=(1100, 60))
dns = net.server("DNS", at=(250, 60), ip="8.8.8.8/24", gateway="8.8.8.1")
web = net.server("WEB", at=(1350, 60), ip="1.1.1.1/24", gateway="1.1.1.254")
isp1["g0/2"].connect(isp2["g0/2"])
isp1["g0/1"].connect(dns["fa0"])
isp2["g0/1"].connect(web["fa0"])
isp1["g0/1"].address = "8.8.8.1/24"
isp2["g0/1"].address = "1.1.1.254/24"
isp1["g0/2"].address = at(ISP_PEER, 1)
isp2["g0/2"].address = at(ISP_PEER, 2)
isp1["g0/0"].address = at(ISP1_HQ, 1)
isp2["g0/0"].address = at(ISP2_HQ, 1)
isp1.config(f"""
router bgp 65001
 neighbor {plain(ISP_PEER, 2)} remote-as 65002
 neighbor {plain(ISP1_HQ, 2)} remote-as 65100
 network 8.8.8.0 mask 255.255.255.0
""")
isp2.config(f"""
router bgp 65002
 neighbor {plain(ISP_PEER, 1)} remote-as 65001
 neighbor {plain(ISP2_HQ, 2)} remote-as 65100
 network 1.1.1.0 mask 255.255.255.0
""")

# --- hq edge ----------------------------------------------------------------
edge1 = net.router("EDGE1", "ISR4331", at=(500, 200))
edge2 = net.router("EDGE2", "2911", at=(1100, 200))
edge1.add_module("NIM-2T", slot=(0, 2))  # Serial0/2/0 and 0/2/1, for the branches
edge1["g0/0/0"].connect(isp1["g0/0"])
edge2["g0/0"].connect(isp2["g0/0"])
edge1["g0/0/0"].address = at(ISP1_HQ, 2)
edge2["g0/0"].address = at(ISP2_HQ, 2)

# HQ address plan
VLANS = {10: ("STAFF", "10.1.10.0/24"), 30: ("SERVERS", "10.1.30.0/24"), 40: ("GUEST", "10.1.40.0/24")}
UPLINKS = {(1, 1): "10.0.1.0/30", (1, 2): "10.0.1.4/30", (2, 1): "10.0.2.0/30", (2, 2): "10.0.2.4/30"}
HQ_WEB = "10.1.30.20"

for e, (edge, pool, isp_net, inside_ports) in enumerate(
    [(edge1, EDGE1_POOL, ISP1_HQ, ["g0/0/1", "g0/0/2"]), (edge2, EDGE2_POOL, ISP2_HQ, ["g0/1", "g0/2"])], 1
):
    p = nw(pool)
    outside = "g0/0/0" if edge is edge1 else "g0/0"
    edge.config(f"""
interface loopback 0
 ip address 10.255.0.{e} 255.255.255.255
interface {outside}
 ip nat outside
ip route {p.network_address} {p.netmask} null0
ip route 0.0.0.0 0.0.0.0 {plain(isp_net, 1)}
access-list 1 permit 10.0.0.0 0.255.255.255
ip nat pool PUBLIC {p.network_address + 10} {p.network_address + 10} netmask {p.netmask}
ip nat inside source list 1 pool PUBLIC overload
router bgp 65100
 neighbor {plain(isp_net, 1)} remote-as {65000 + e}
 network {p.network_address} mask {p.netmask}
router ospf 1
 router-id 10.255.0.{e}
 network 10.255.0.{e} 0.0.0.0 area 0
""")
    for c, port in enumerate(inside_ports, 1):
        edge[port].address = at(UPLINKS[(e, c)], 1)
        edge.config(f"interface {port}\n ip nat inside\nrouter ospf 1\n network {wild(UPLINKS[(e, c)])} area 0")
# One default, from EDGE1: replies must leave by the edge holding their NAT
# entry. (Packet Tracer 8.2 refuses `default-information originate` with
# `metric` or `metric-type`, so two weighted defaults aren't an option.)
edge1.config("router ospf 1\n default-information originate")
edge1.config(f"ip nat inside source static {HQ_WEB} 192.0.2.80")

# --- hq campus --------------------------------------------------------------
cores = [net.multilayer(f"CORE{i}", "3650-24PS", at=(650 + 300 * (i - 1), 340)) for i in (1, 2)]
for c, core in enumerate(cores, 1):
    me = 1 + c  # CORE1 .2, CORE2 .3; HSRP .1
    cfg = [
        "ip routing",
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan 10,30,40 priority {4096 * c}",
        "interface range g1/0/23 - 24",
        " switchport mode trunk",
        " channel-group 1 mode active",
        "interface port-channel 1",
        " switchport mode trunk",
        "interface loopback 0",
        f" ip address 10.255.1.{c} 255.255.255.255",
        "ip access-list extended GUEST-IN",
        " permit udp any any eq 67",
        " permit udp any host 8.8.8.8 eq 53",
        " deny ip any 10.0.0.0 0.255.255.255",
        " permit ip any any",
    ]
    for e in (1, 2):
        port = f"g1/0/{e}"
        cfg += [
            f"interface {port}",
            " no switchport",
            f" ip address {at(UPLINKS[(e, c)], 2).replace('/30', ' 255.255.255.252')}",
        ]
    cfg += [f"ip route 0.0.0.0 0.0.0.0 {plain(UPLINKS[(2, c)], 1)} 250"]  # floating, via EDGE2
    for vid, (name, cidr) in VLANS.items():
        n_ = nw(cidr)
        cfg += [
            f"vlan {vid}",
            f" name {name}",
            f"interface vlan {vid}",
            f" ip address {n_.network_address + me} {n_.netmask}",
            f" standby 1 ip {n_.network_address + 1}",
            f" standby 1 priority {110 if c == 1 else 100}",
            " standby 1 preempt",
        ]
        if name == "GUEST":
            cfg += [" ip access-group GUEST-IN in"]
    cfg += [
        "router ospf 1",
        f" router-id 10.255.1.{c}",
        f" network 10.255.1.{c} 0.0.0.0 area 0",
        f" network {wild(UPLINKS[(1, c)])} area 0",
        f" network {wild(UPLINKS[(2, c)])} area 0",
    ]
    cfg += [f" network {wild(cidr)} area 0" for _, cidr in VLANS.values()]
    core.config(cfg)
    edge1[["g0/0/1", "g0/0/2"][c - 1]].connect(core["g1/0/1"])
    edge2[["g0/1", "g0/2"][c - 1]].connect(core["g1/0/2"])
cores[0]["g1/0/23"].connect(cores[1]["g1/0/23"])
cores[0]["g1/0/24"].connect(cores[1]["g1/0/24"])

cores[0].config(
    "".join(
        f"""
ip dhcp excluded-address {plain(VLANS[v][1], 1)} {plain(VLANS[v][1], 19)}
ip dhcp pool {VLANS[v][0]}
 network {nw(VLANS[v][1]).network_address} {nw(VLANS[v][1]).netmask}
 default-router {plain(VLANS[v][1], 1)}
 dns-server 8.8.8.8
"""
        for v in (10, 40)
    )
)

access = []
for a in range(2):
    sw = net.switch(f"ACC{a + 1}", at=(650 + 300 * a, 480))
    sw.config("interface range g0/1 - 2\n switchport mode trunk")
    for c, core in enumerate(cores):
        sw[f"g0/{c + 1}"].connect(core[f"g1/0/{3 + a}"])
    access.append(sw)
for core in cores:
    core.config("interface range g1/0/3 - 4\n switchport mode trunk")

staff = [net.pc(f"STAFF{i + 1}", at=(520 + 90 * i, 600)) for i in range(2)]
guest = net.laptop("GUEST1", at=(700, 600))
for i, d in enumerate(staff + [guest]):
    d.use_dhcp()
    access[0][f"fa0/{i + 1}"].connect(d["fa0"])
    access[0].config(
        f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {40 if d is guest else 10}"
    )
hq_web = net.server("HQ-WEB", at=(880, 600), ip=f"{HQ_WEB}/24", gateway="10.1.30.1")
hq_files = net.server("HQ-FILES", at=(980, 600), ip="10.1.30.21/24", gateway="10.1.30.1")
for i, s in enumerate((hq_web, hq_files)):
    access[1][f"fa0/{i + 1}"].connect(s["fa0"])
    access[1].config(f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan 30")

# --- wan: branch 1, OSPF area 1 ---------------------------------------------
WAN1, WAN2 = "10.0.10.0/30", "10.0.20.0/30"
br1 = net.router("BR1", "1841", at=(200, 420))
br1.add_module("WIC-2T", slot=(0, 0))
edge1["se0/2/0"].connect(br1["se0/0/0"])  # EDGE1 is the DCE end
edge1["se0/2/0"].address = at(WAN1, 1)
br1["se0/0/0"].address = at(WAN1, 2)
edge1.config(f"interface se0/2/0\n ip nat inside\nrouter ospf 1\n network {wild(WAN1)} area 1")
B1 = {10: "10.2.10.0/24", 40: "10.2.40.0/24"}
br1_sw = net.switch("BR1-SW", at=(200, 540))
br1["fa0/0"].connect(br1_sw["g0/1"])
br1_sw.config("interface g0/1\n switchport mode trunk")
br1.config(
    "interface fa0/0\n no shutdown\n"
    + "".join(
        f"""
interface fa0/0.{v}
 encapsulation dot1Q {v}
 ip address {plain(c, 1)} {nw(c).netmask}
ip dhcp excluded-address {plain(c, 1)} {plain(c, 9)}
ip dhcp pool BR1-{v}
 network {nw(c).network_address} {nw(c).netmask}
 default-router {plain(c, 1)}
 dns-server 8.8.8.8
"""
        for v, c in B1.items()
    )
    + f"""
router ospf 1
 router-id 10.255.2.1
 network {wild(WAN1)} area 1
"""
    + "".join(f" network {wild(c)} area 1\n" for c in B1.values())
)
for i, v in enumerate((10, 10, 40)):
    d = net.pc(f"BR1-PC{i + 1}", at=(100 + 100 * i, 640))
    d.use_dhcp()
    br1_sw[f"fa0/{i + 1}"].connect(d["fa0"])
    br1_sw.config(f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {v}")

# --- wan: branch 2, EIGRP 100 -----------------------------------------------
br2 = net.router("BR2", "2911", at=(1350, 420))
br2.add_module("HWIC-2T", slot=(0, 0))
edge1["se0/2/1"].connect(br2["se0/0/0"])
edge1["se0/2/1"].address = at(WAN2, 1)
br2["se0/0/0"].address = at(WAN2, 2)
edge1.config(f"""
interface se0/2/1
 ip nat inside
router eigrp 100
 no auto-summary
 network {wild(WAN2)}
 redistribute ospf 1 metric 1544 2000 255 1 1500
 redistribute static metric 1544 2000 255 1 1500
router ospf 1
 redistribute eigrp 100 subnets
""")
DATA, VOICE, CME = "10.3.50.0/24", "10.3.60.0/24", "10.3.60.5"
br2_sw = net.multilayer("BR2-SW", "3560-24PS", at=(1350, 540))  # PoE for the phones
br2["g0/0"].connect(br2_sw["g0/1"])
br2_sw.config("cdp run\ninterface g0/1\n switchport trunk encapsulation dot1q\n switchport mode trunk")
br2.config(
    "interface g0/0\n no shutdown\n"
    + "".join(
        f"""
interface g0/0.{v}
 encapsulation dot1Q {v}
 ip address {plain(c, 1)} {nw(c).netmask}
ip dhcp excluded-address {plain(c, 1)} {plain(c, 9)}
"""
        for v, c in ((50, DATA), (60, VOICE))
    )
    + f"""
ip dhcp pool DATA
 network {nw(DATA).network_address} {nw(DATA).netmask}
 default-router {plain(DATA, 1)}
 dns-server 8.8.8.8
ip dhcp pool VOICE
 network {nw(VOICE).network_address} {nw(VOICE).netmask}
 default-router {plain(VOICE, 1)}
 option 150 ip {CME}
router eigrp 100
 no auto-summary
 network {wild(WAN2)}
 network {wild(DATA)}
 network {wild(VOICE)}
"""
)
PHONES = 3
cme = net.router("CME", "2811", at=(1550, 540))
cme["fa0/0"].connect(br2_sw["fa0/24"])
br2_sw.config("interface fa0/24\n switchport mode access\n switchport access vlan 60")
br2_sw.add_vlan(50, "DATA")
br2_sw.add_vlan(60, "VOICE")
cme["fa0/0"].address = f"{CME}/24"
cme.config(
    f"""
ip route 0.0.0.0 0.0.0.0 {plain(VOICE, 1)}
telephony-service
 max-ephones {PHONES}
 max-dn {PHONES}
 ip source-address {CME} port 2000
 auto assign 1 to {PHONES}
"""
    + "".join(f"ephone-dn {d}\n number {2000 + d}\n" for d in range(1, PHONES + 1))
)
for p in range(PHONES):
    x = 1250 + 110 * p
    phone = net.phone(f"BR2-PHONE{p + 1}", at=(x, 640))
    pc = net.pc(f"BR2-PC{p + 1}", at=(x, 730))
    pc.use_dhcp()
    br2_sw[f"fa0/{p + 1}"].connect(phone["Switch"])
    phone["PC"].connect(pc["fa0"])
    br2_sw.config(
        f"interface fa0/{p + 1}\n switchport mode access\n switchport access vlan 50\n switchport voice vlan 60"
    )

# --- drawings ---------------------------------------------------------------
net.around(isp1, isp2, dns, web, shape="rectangle", outline="grey", label="INTERNET (eBGP)", pad=50)
net.around(
    edge1,
    edge2,
    *cores,
    *access,
    staff[0],
    guest,
    hq_web,
    hq_files,
    *staff,
    shape="rectangle",
    outline="blue",
    label="HQ: OSPF area 0",
    pad=40,
)
net.around(
    br1,
    br1_sw,
    *[net.device(f"BR1-PC{i + 1}") for i in range(3)],
    shape="rectangle",
    outline="green",
    label="BRANCH 1: OSPF area 1",
    pad=40,
)
net.around(
    br2,
    br2_sw,
    cme,
    *[d for d in net.devices if d.name.startswith(("BR2-PHONE", "BR2-PC"))],
    shape="rectangle",
    outline="orange",
    label="BRANCH 2: EIGRP 100",
    pad=40,
)

# ping checks, listed under the workspace: click one once BGP, OSPF and EIGRP have settled
net.ping("BR1-PC1", "DNS", scenario="Branch 1 to the internet (NAT)")
net.ping("BR2-PC1", "WEB", scenario="Branch 2 to the internet (NAT)")
net.ping("STAFF1", "WEB", scenario="HQ staff (DHCP) to the internet")
net.ping("WEB", "HQ-WEB", ip="192.0.2.80", scenario="Internet to the HQ web server (static NAT)")
net.ping("GUEST1", "DNS", scenario="Guest to the internet")
net.ping("GUEST1", "HQ-WEB", ip=HQ_WEB, scenario="Guest to HQ servers: should FAIL")

net.save("enterprise.pkt")
print(f"enterprise.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.shapes)} shapes")
