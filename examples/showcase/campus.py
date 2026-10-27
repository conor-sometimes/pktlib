"""A university campus: five buildings, a VLAN per department, HSRP cores, guest network behind ACLs.

    uv run python examples/showcase/campus.py               # writes campus.pkt

internet   an ISP router (2911) and a public web server on 8.8.8.8
edge       ISR4331: NAT overload onto 198.51.100.10, OSPF to both cores,
           and the default route into OSPF
core       two 3650s: an SVI per VLAN with an HSRP gateway on .1, rapid PVST
           with CORE1 as root, an LACP trunk between them, OSPF area 0, DHCP
           for every user VLAN on CORE1
buildings  ENGINEERING, SCIENCE, LIBRARY, ADMIN and RESIDENCES, a 2960 in
           each, trunked to both cores; the server room holds WEB, LMS and
           RECORDS (the student records system)
policy     GUEST (VLAN 60) reaches the internet and nothing internal;
           RESIDENCES (VLAN 50) reaches everything except RECORDS

Every department is one line in VLANS; add one and its SVIs, DHCP pool and
OSPF network follow. Addresses: VLAN n is 10.20.n.0/24, gateway .1.

Check in Packet Tracer:
  CORE1# show standby brief            -> Active on every VLAN (CORE2 Standby)
  CORE1# show etherchannel summary     -> Po1(SU) with Gi1/0/23 and Gi1/0/24 (P)
  CORE1# show ip ospf neighbor         -> EDGE and CORE2 FULL
  CORE1# show ip dhcp binding          -> a lease for every PC and laptop
  EDGE# show ip nat translations       -> after the internet pings, entries on 198.51.100.10
  ENG-PC1 ping 10.20.100.20 (LMS)      -> success
  GUEST1  ping 8.8.8.8 works; ping 10.20.100.30 (RECORDS) fails
  RES-PC1 ping 10.20.100.30 fails; ping 10.20.100.10 (WEB) works
  Or click the ping scenarios under the workspace.
"""

import ipaddress

import pktlib

# vid: department; each building's switch carries the VLANs of its hosts
VLANS = {
    10: "ENGINEERING",
    20: "SCIENCE",
    30: "LIBRARY",
    40: "ADMIN",
    50: "RESIDENCES",
    60: "GUEST",
    100: "SERVERS",
}
DHCP_VLANS = [10, 20, 30, 40, 50, 60]
# building: [(host name, kind, vlan), ...]
BUILDINGS = {
    "ENGINEERING": [("ENG-PC1", "pc", 10), ("ENG-PC2", "pc", 10), ("ENG-PC3", "pc", 10)],
    "SCIENCE": [("SCI-PC1", "pc", 20), ("SCI-PC2", "pc", 20), ("SCI-PRINTER", "printer", 20)],
    "LIBRARY": [("LIB-PC1", "pc", 30), ("LIB-PC2", "pc", 30), ("GUEST1", "laptop", 60)],
    "ADMIN": [("ADMIN-PC1", "pc", 40), ("ADMIN-PC2", "pc", 40), ("ADMIN-PRINTER", "printer", 40)],
    "RESIDENCES": [("RES-PC1", "pc", 50), ("RES-LAPTOP", "laptop", 50), ("GUEST2", "laptop", 60)],
    "SERVER ROOM": [("WEB", "server", 100), ("LMS", "server", 100), ("RECORDS", "server", 100)],
}
STATIC = {"SCI-PRINTER": 5, "ADMIN-PRINTER": 5, "WEB": 10, "LMS": 20, "RECORDS": 30}
RECORDS = "10.20.100.30"
PUBLIC = "198.51.100.10"

net = pktlib.new()


def lan(vid: int) -> ipaddress.IPv4Network:
    return ipaddress.IPv4Network(f"10.20.{vid}.0/24")


def addr(vid: int, n: int) -> str:
    return str(lan(vid).network_address + n)


# --- internet ---------------------------------------------------------------
isp = net.router("ISP", "2911", at=(900, 40))
inet = net.server("INTERNET", at=(1150, 40), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].address = "203.0.113.1/30"
isp.config(f"ip route {PUBLIC} 255.255.255.255 203.0.113.2")  # the campus's one public address

# --- edge -------------------------------------------------------------------
edge = net.router("EDGE", "ISR4331", at=(900, 160))
edge["g0/0/2"].connect(isp["g0/0"])
edge["g0/0/2"].address = "203.0.113.2/30"
edge["g0/0/0"].address = "10.0.0.1/30"
edge["g0/0/1"].address = "10.0.0.5/30"
edge.config(f"""
interface g0/0/2
 ip nat outside
interface g0/0/0
 ip nat inside
interface g0/0/1
 ip nat inside
access-list 1 permit 10.0.0.0 0.255.255.255
ip nat pool CAMPUS {PUBLIC} {PUBLIC} netmask 255.255.255.0
ip nat inside source list 1 pool CAMPUS overload
ip route 0.0.0.0 0.0.0.0 203.0.113.1
router ospf 1
 router-id 10.255.0.1
 network 10.0.0.0 0.0.0.7 area 0
 default-information originate
""")

# --- core -------------------------------------------------------------------
UPLINKS = {name: f"g1/0/{2 + i}" for i, name in enumerate(BUILDINGS)}  # one per building
cores = [net.multilayer(f"CORE{c}", "3650-24PS", at=(600 + 600 * (c - 1), 300)) for c in (1, 2)]
for c, core in enumerate(cores, 1):
    edge[f"g0/0/{c - 1}"].connect(core["g1/0/1"])
    cfg = [
        "ip routing",
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan {','.join(map(str, VLANS))} priority {4096 * c}",
        "interface range g1/0/23 - 24",
        " switchport mode trunk",
        " channel-group 1 mode active",
        "interface port-channel 1",
        " switchport mode trunk",
        "interface g1/0/1",
        " no switchport",
        f" ip address 10.0.0.{4 * c - 2} 255.255.255.252",
        # guests: DHCP and DNS, then the internet, never the campus
        "ip access-list extended GUEST-IN",
        " permit udp any any eq 67",
        " permit udp any host 8.8.8.8 eq 53",
        " deny ip any 10.0.0.0 0.255.255.255",
        " permit ip any any",
        # residences: everything but the records system
        "ip access-list extended RESIDENCES-IN",
        f" deny ip any host {RECORDS}",
        " permit ip any any",
        "router ospf 1",
        f" router-id 10.255.0.{1 + c}",
        f" network 10.0.0.{4 * (c - 1)} 0.0.0.3 area 0",
    ]
    for vid, name in VLANS.items():
        cfg += [
            f"vlan {vid}",
            f" name {name}",
            f"interface vlan {vid}",
            f" ip address {addr(vid, 1 + c)} 255.255.255.0",  # CORE1 .2, CORE2 .3
            f" standby 1 ip {addr(vid, 1)}",
            f" standby 1 priority {110 if c == 1 else 100}",
            " standby 1 preempt",
        ]
        if name == "GUEST":
            cfg.append(" ip access-group GUEST-IN in")
        if name == "RESIDENCES":
            cfg.append(" ip access-group RESIDENCES-IN in")
        cfg += ["router ospf 1", f" network {lan(vid).network_address} 0.0.0.255 area 0"]
    cfg += [f"interface {port}\n switchport mode trunk" for port in UPLINKS.values()]
    core.config(cfg)
cores[0]["g1/0/23"].connect(cores[1]["g1/0/23"])
cores[0]["g1/0/24"].connect(cores[1]["g1/0/24"])

# DHCP for the user VLANs, on CORE1; .1 to .19 are kept for gateways and printers
for vid in DHCP_VLANS:
    cores[0].config(f"""
ip dhcp excluded-address {addr(vid, 1)} {addr(vid, 19)}
ip dhcp pool {VLANS[vid]}
 network {lan(vid).network_address} {lan(vid).netmask}
 default-router {addr(vid, 1)}
 dns-server 8.8.8.8
""")

# --- buildings --------------------------------------------------------------
COLOURS = ["blue", "green", "purple", "orange", "red", "grey"]
for b, (building, hosts) in enumerate(BUILDINGS.items()):
    x = 120 + 280 * b
    sw = net.switch(f"{building.split()[0][:3]}-SW", at=(x + 80, 470))
    sw.config("spanning-tree mode rapid-pvst\ninterface range g0/1 - 2\n switchport mode trunk")
    for c, core in enumerate(cores):
        sw[f"g0/{c + 1}"].connect(core[UPLINKS[building]])
    members = [sw]
    for h, (name, kind, vid) in enumerate(hosts):
        make = {"pc": net.pc, "laptop": net.laptop, "printer": net.printer, "server": net.server}[kind]
        d = make(name, at=(x + 80 * h, 600))
        if name in STATIC:
            d.set_ip(f"{addr(vid, STATIC[name])}/24", addr(vid, 1))
        else:
            d.use_dhcp()
        sw[f"fa0/{h + 1}"].connect(d["fa0"])
        sw.config(
            f"interface fa0/{h + 1}\n switchport mode access\n switchport access vlan {vid}\n spanning-tree portfast"
        )
        members.append(d)
    vids = sorted({vid for _, _, vid in hosts})
    for v in vids:
        sw.add_vlan(v, VLANS[v])  # named, as on the cores
    net.around(*members, shape="rectangle", outline=COLOURS[b], pad=35)
    # the label above the box, not beside it, so it doesn't run into the next building
    net.note(f"{building}\nVLAN {', '.join(map(str, vids))}", at=(x - 30, 390))

# --- drawings ---------------------------------------------------------------
net.around(isp, inet, shape="rectangle", outline="grey", label="INTERNET", pad=40)
net.around(edge, *cores, shape="rectangle", outline="blue", label="CORE: OSPF area 0, HSRP on every VLAN", pad=40)
net.note(
    "Every VLAN is 10.20.<vlan>.0/24, gateway .1 (HSRP), CORE1 .2, CORE2 .3.\n"
    "GUEST (60): internet only. RESIDENCES (50): everything but RECORDS.",
    at=(60, 80),
)

# --- ping checks ------------------------------------------------------------
net.ping("ENG-PC1", "LMS", scenario="Departments to campus servers")
net.ping("SCI-PC1", "WEB", scenario="Departments to campus servers")
net.ping("ADMIN-PC1", "RECORDS", scenario="Departments to campus servers")
net.ping("LIB-PC1", "SCI-PRINTER", scenario="Departments to campus servers")
net.ping("ENG-PC2", "INTERNET", scenario="Campus to internet")
net.ping("RES-PC1", "INTERNET", scenario="Campus to internet")
net.ping("GUEST1", "INTERNET", scenario="Guest to internet")
net.ping("GUEST2", "INTERNET", scenario="Guest to internet")
net.ping("GUEST1", "RECORDS", scenario="Guest to campus: should FAIL")
net.ping("GUEST2", "WEB", scenario="Guest to campus: should FAIL")
net.ping("RES-PC1", "RECORDS", scenario="Residences to records: should FAIL")

net.save("campus.pkt")
print(f"campus.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
