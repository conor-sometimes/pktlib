"""A small data centre and an office, behind one edge router.

    uv run python examples/showcase/datacenter.py            # writes datacenter.pkt

  internet   ISP router (2911) and a web server on 8.8.8.8
  edge       ISR4331: OSPF to both cores, default route to the ISP
  core       two 3650s: an SVI per VLAN with an HSRP virtual gateway, OSPF,
             an LACP EtherChannel trunk between them, DHCP for the office
  dc         four 2960 leaves, each trunked to both cores, 12 servers in
             web / app / db VLANs
  office     a PoE 3560 access switch, 7960 IP phones with a PC behind each
             (voice VLAN), printers, laptops; a 2811 running CME so the
             phones register and get extensions 1001-1006

Everything is generated: change LEAVES, PHONES or the VLAN table and run it again.
"""

import ipaddress

import pktlib

VLANS = {
    10: ("WEB", "10.10.10.0/24"),
    20: ("APP", "10.10.20.0/24"),
    30: ("DB", "10.10.30.0/24"),
    100: ("OFFICE", "10.20.100.0/24"),
    110: ("VOICE", "10.20.110.0/24"),
}
LEAVES = 4
SERVERS = [["WEB", "WEB", "APP"], ["WEB", "APP", "DB"], ["APP", "DB", "DB"], ["WEB", "APP", "DB"]]
PHONES = 6
CME = "10.20.110.5"

net = pktlib.new()
vid_of = {name: vid for vid, (name, _) in VLANS.items()}
lan = {vid: ipaddress.ip_network(cidr) for vid, (_, cidr) in VLANS.items()}


def host(vid: int, n: int) -> str:
    return str(lan[vid].network_address + n)


# --- internet ---------------------------------------------------------------
isp = net.router("ISP", "2911", at=(700, 40))
inet_sw = net.switch("INET-SW", at=(950, 40))
web = net.server("INTERNET-WEB", at=(1150, 40), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet_sw["g0/1"])
inet_sw["fa0/1"].connect(web["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].address = "203.0.113.1/30"
isp.config("ip route 10.0.0.0 255.0.0.0 203.0.113.2")

# --- edge -------------------------------------------------------------------
edge = net.router("EDGE", "ISR4331", at=(700, 150))
edge["g0/0/2"].connect(isp["g0/0"])
edge["g0/0/2"].address = "203.0.113.2/30"
edge["g0/0/0"].address = "10.0.0.1/30"
edge["g0/0/1"].address = "10.0.0.5/30"
edge.config("""
ip route 0.0.0.0 0.0.0.0 203.0.113.1
router ospf 1
 router-id 1.1.1.1
 network 10.0.0.0 0.0.0.7 area 0
 default-information originate
""")

# --- core -------------------------------------------------------------------
cores = [net.multilayer(f"CORE{i}", "3650-24PS", at=(450 + 500 * (i - 1), 280)) for i in (1, 2)]
for i, core in enumerate(cores):
    edge[f"g0/0/{i}"].connect(core["g1/0/1"])
    me = 2 + i  # CORE1 .2, CORE2 .3; the HSRP gateway is .1
    cfg = [
        "ip routing",
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan {','.join(map(str, VLANS))} priority {4096 if i == 0 else 8192}",
        "interface g1/0/1",
        " no switchport",
        f" ip address 10.0.0.{2 + 4 * i} 255.255.255.252",
        " no shutdown",
        # the cores share an LACP EtherChannel trunk
        "interface range g1/0/23 - 24",
        " switchport mode trunk",
        " channel-group 1 mode active",
        "interface port-channel 1",
        " switchport mode trunk",
    ]
    for vid, (name, _) in VLANS.items():
        cfg += [
            f"vlan {vid}",
            f" name {name}",
            f"interface vlan {vid}",
            f" ip address {host(vid, me)} {lan[vid].netmask}",
            f" standby 1 ip {host(vid, 1)}",
            f" standby 1 priority {110 if i == 0 else 100}",
            " standby 1 preempt",
            " no shutdown",
        ]
    cfg += ["router ospf 1", f" router-id {i + 2}.{i + 2}.{i + 2}.{i + 2}", f" network 10.0.0.{4 * i} 0.0.0.3 area 0"]
    cfg += [f" network {lan[v].network_address} 0.0.0.255 area 0" for v in VLANS]
    core.config(cfg)
cores[0]["g1/0/23"].connect(cores[1]["g1/0/23"])
cores[0]["g1/0/24"].connect(cores[1]["g1/0/24"])

# DHCP for the office lives on CORE1
cores[0].config(f"""
ip dhcp excluded-address {host(100, 1)} {host(100, 20)}
ip dhcp excluded-address {host(110, 1)} {host(110, 20)}
ip dhcp pool OFFICE
 network {lan[100].network_address} {lan[100].netmask}
 default-router {host(100, 1)}
 dns-server 8.8.8.8
ip dhcp pool VOICE
 network {lan[110].network_address} {lan[110].netmask}
 default-router {host(110, 1)}
 option 150 ip {CME}
""")

# --- data centre ------------------------------------------------------------
for n in range(LEAVES):
    x = 150 + n * 240
    leaf = net.switch(f"LEAF{n + 1}", at=(x, 440))
    leaf.config("interface range g0/1 - 2\n switchport mode trunk")
    for i, core in enumerate(cores):
        leaf[f"g0/{i + 1}"].connect(core[f"g1/0/{2 + n}"])
    for j, role in enumerate(SERVERS[n]):
        vid = vid_of[role]
        k = sum(1 for m in range(n) for r in SERVERS[m] if r == role) + SERVERS[n][:j].count(role) + 1
        srv = net.server(f"{role}{k}", at=(x - 80 + j * 80, 560), ip=f"{host(vid, 100 + k)}/24", gateway=host(vid, 1))
        leaf[f"fa0/{j + 1}"].connect(srv["fa0"])
        leaf.config(f"interface fa0/{j + 1}\n switchport mode access\n switchport access vlan {vid}")
    for core in cores:
        core.config(f"interface g1/0/{2 + n}\n switchport mode trunk")
for core in cores:
    core.config("interface g1/0/6\n switchport mode trunk")

# --- office -----------------------------------------------------------------
osw = net.multilayer("OFFICE-SW", "3560-24PS", at=(1300, 440))  # PoE, so the phones power up
# Packet Tracer 8.2 ships the 3560 with `no cdp run`; the phones learn their
# voice VLAN over CDP, so without this they never get a voice address or register.
osw.config("cdp run\ninterface range g0/1 - 2\n switchport mode trunk")
for i, core in enumerate(cores):
    osw[f"g0/{i + 1}"].connect(core["g1/0/6"])
for p in range(PHONES):
    x, y = 1180 + (p % 3) * 120, 560 + (p // 3) * 170
    phone = net.phone(f"PHONE{p + 1}", at=(x, y))
    pc = net.pc(f"DESK{p + 1}", at=(x, y + 80))
    pc.use_dhcp()
    osw[f"fa0/{p + 1}"].connect(phone["Switch"])
    phone["PC"].connect(pc["fa0"])
    osw.config(
        f"interface fa0/{p + 1}\n switchport mode access\n switchport access vlan 100\n switchport voice vlan 110"
    )
for i in range(2):
    pr = net.printer(f"PRINTER{i + 1}", at=(1560, 560 + i * 120), ip=f"{host(100, 11 + i)}/24", gateway=host(100, 1))
    osw[f"fa0/{10 + i}"].connect(pr["fa0"])
    lt = net.laptop(f"LAPTOP{i + 1}", at=(1680, 560 + i * 120))
    lt.use_dhcp()
    osw[f"fa0/{12 + i}"].connect(lt["fa0"])
for port in (10, 11, 12, 13):
    osw.config(f"interface fa0/{port}\n switchport mode access\n switchport access vlan 100")

cme = net.router("CME", "2811", at=(1560, 330))
cme["fa0/0"].connect(osw["fa0/24"])
osw.config("interface fa0/24\n switchport mode access\n switchport access vlan 110")
cme["fa0/0"].address = f"{CME}/24"
cme.config(
    f"""
ip route 0.0.0.0 0.0.0.0 {host(110, 1)}
telephony-service
 max-ephones {PHONES}
 max-dn {PHONES}
 ip source-address {CME} port 2000
 auto assign 1 to {PHONES}
"""
    + "".join(f"ephone-dn {d}\n number {1000 + d}\n" for d in range(1, PHONES + 1))
)

# --- drawings ---------------------------------------------------------------
net.around(isp, inet_sw, web, shape="rectangle", outline="grey", label="INTERNET", pad=50)
net.around(edge, *cores, outline="blue", label="OSPF area 0", pad=40)
dc = [net.device(f"LEAF{n + 1}") for n in range(LEAVES)] + [
    d for d in net.devices if d.kind == "Server" and d.name != "INTERNET-WEB"
]
net.around(*dc, shape="rectangle", outline="green", label="DATA CENTRE", pad=50)
office = [osw, cme] + [d for d in net.devices if d.name.startswith(("PHONE", "DESK", "PRINTER", "LAPTOP"))]
net.around(*office, shape="rectangle", outline="orange", label="OFFICE", pad=50)

# ping checks, listed under the workspace: click one once OSPF and HSRP have settled
net.ping("WEB1", "INTERNET-WEB", scenario="Data centre to the internet")
net.ping("WEB1", "DB1", scenario="Web tier to database tier")
net.ping("APP1", "DB2", scenario="App tier to database tier")
net.ping("DESK1", "DB1", scenario="Office PC (DHCP) to the databases")

net.save("datacenter.pkt")
print(f"datacenter.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.shapes)} shapes")
