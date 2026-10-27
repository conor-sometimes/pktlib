"""A hospital and its outpatient clinic, with clinical, medical device, admin and guest networks kept apart.

    uv run python examples/showcase/hospital.py             # writes hospital.pkt

internet   an ISP router (2911) and a public server on 8.8.8.8
edge       a 2911 with an HWIC-2T: NAT overload onto 203.0.113.2, the
           default route into OSPF, a serial link to the clinic
hospital   one 3650 core routing seven VLANs, OSPF area 0, DHCP for staff
           and guests; a 2960 per floor (EMERGENCY, WARDS, ADMIN) and one
           in the data centre
clinic     a 2911 across town on the serial WAN: router on a stick, DHCP,
           the same rules for its admin VLAN
policy     ACLs on the gateways, inbound:
             CLINICAL    reaches everything
             MEDICAL     (pumps, monitors) only clinical and records
             ADMIN       admin servers and the internet; never patient
                         records, clinical desks or medical devices
             GUEST       DHCP, DNS and the internet only

Addresses: hospital VLAN n is 10.30.n.0/24, clinic VLAN n is 10.31.n.0/24,
gateway .1 in each.

Check in Packet Tracer:
  CORE# show ip ospf neighbor          -> EDGE FULL
  CLINIC# show ip ospf neighbor        -> EDGE FULL over Serial0/0/0
  CORE# show access-lists              -> match counts go up as the pings run
  EDGE# show ip nat translations       -> entries on 203.0.113.2 after the internet pings
  ED-PC1 ping 10.30.40.10 (EHR)        -> success
  BILLING-PC1 ping 10.30.40.10         -> fails (ADMIN-IN)
  PUMP1 ping 8.8.8.8                   -> fails (MEDICAL-IN); ping 10.30.40.11 (PACS) works
  VISITOR1 ping 8.8.8.8 works; ping 10.30.20.10 (PUMP1) fails
  Or click the ping scenarios under the workspace.
"""

import pktlib

VLANS = {
    10: "CLINICAL",
    20: "MEDICAL",
    30: "ADMIN",
    40: "RECORDS",
    50: "ADMIN-SERVERS",
    60: "GUEST",
    99: "MGMT",
}
DHCP = [10, 30, 60]
EHR, PACS = "10.30.40.10", "10.30.40.11"

# Inbound on each gateway. Wildcards cover the hospital (10.30) and clinic (10.31) alike.
ACLS = {
    "MEDICAL-IN": [
        " permit ip any 10.30.10.0 0.0.0.255",
        " permit ip any 10.31.10.0 0.0.0.255",
        " permit ip any 10.30.40.0 0.0.0.255",
        " deny ip any any",
    ],
    "ADMIN-IN": [
        " permit udp any any eq 67",
        " deny ip any 10.30.10.0 0.0.0.255",
        " deny ip any 10.31.10.0 0.0.0.255",
        " deny ip any 10.30.20.0 0.0.0.255",
        " deny ip any 10.30.40.0 0.0.0.255",
        " permit ip any any",
    ],
    "GUEST-IN": [
        " permit udp any any eq 67",
        " permit udp any host 8.8.8.8 eq 53",
        " deny ip any 10.0.0.0 0.255.255.255",
        " permit ip any any",
    ],
}
ACL_ON = {20: "MEDICAL-IN", 30: "ADMIN-IN", 60: "GUEST-IN"}

# floor: [(name, kind, vlan, static host number or None for DHCP)]
FLOORS = {
    "EMERGENCY": [
        ("ED-PC1", "pc", 10, None),
        ("ED-PC2", "pc", 10, None),
        ("MONITOR1", "pc", 20, 20),
        ("MONITOR2", "pc", 20, 21),
    ],
    "WARDS": [
        ("WARD-PC1", "pc", 10, None),
        ("PUMP1", "pc", 20, 10),
        ("PUMP2", "pc", 20, 11),
        ("VISITOR1", "laptop", 60, None),
    ],
    "ADMIN": [
        ("BILLING-PC1", "pc", 30, None),
        ("HR-PC1", "pc", 30, None),
        ("ADMIN-PRINTER", "printer", 30, 5),
        ("VISITOR2", "laptop", 60, None),
    ],
    "DATA CENTRE": [
        ("EHR", "server", 40, 10),
        ("PACS", "server", 40, 11),
        ("BILLING", "server", 50, 10),
        ("MAIL", "server", 50, 11),
    ],
}

net = pktlib.new()


def acl_lines() -> list[str]:
    out = []
    for name, rules in ACLS.items():
        out += [f"ip access-list extended {name}", *rules]
    return out


# --- internet and edge ------------------------------------------------------
isp = net.router("ISP", "2911", at=(700, 40))
inet = net.server("INTERNET", at=(950, 40), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].address = "203.0.113.1/30"
isp.config("ip route 203.0.113.0 255.255.255.0 203.0.113.2")  # the hospital's public block

edge = net.router("EDGE", "2911", at=(700, 170))
edge.add_module("HWIC-2T", slot=(0, 0))
edge["g0/0"].connect(isp["g0/0"])
edge["g0/0"].address = "203.0.113.2/30"
edge["g0/1"].address = "10.30.255.1/30"
edge.config("""
interface g0/0
 ip nat outside
interface g0/1
 ip nat inside
interface se0/0/0
 ip nat inside
access-list 1 permit 10.0.0.0 0.255.255.255
ip nat inside source list 1 interface GigabitEthernet0/0 overload
ip route 0.0.0.0 0.0.0.0 203.0.113.1
router ospf 1
 router-id 10.30.254.1
 network 10.30.255.0 0.0.0.3 area 0
 network 10.31.255.0 0.0.0.3 area 0
 default-information originate
""")

# --- hospital core ----------------------------------------------------------
core = net.multilayer("CORE", "3650-24PS", at=(700, 300))
edge["g0/1"].connect(core["g1/0/1"])
cfg = [
    "ip routing",
    "interface g1/0/1",
    " no switchport",
    " ip address 10.30.255.2 255.255.255.252",
    *acl_lines(),
    "router ospf 1",
    " router-id 10.30.254.2",
    " network 10.30.255.0 0.0.0.3 area 0",
]
for vid, name in VLANS.items():
    cfg += [f"vlan {vid}", f" name {name}", f"interface vlan {vid}", f" ip address 10.30.{vid}.1 255.255.255.0"]
    if vid in ACL_ON:
        cfg.append(f" ip access-group {ACL_ON[vid]} in")
    cfg += ["router ospf 1", f" network 10.30.{vid}.0 0.0.0.255 area 0"]
for vid in DHCP:
    cfg += [
        f"ip dhcp excluded-address 10.30.{vid}.1 10.30.{vid}.19",
        f"ip dhcp pool {VLANS[vid]}",
        f" network 10.30.{vid}.0 255.255.255.0",
        f" default-router 10.30.{vid}.1",
        " dns-server 8.8.8.8",
    ]
core.config(cfg)

COLOURS = {"EMERGENCY": "red", "WARDS": "orange", "ADMIN": "purple", "DATA CENTRE": "green"}
for f, (floor, hosts) in enumerate(FLOORS.items()):
    x = 120 + 380 * f
    sw = net.switch(f"{floor.split()[0][:4]}-SW", at=(x + 120, 450))
    sw["g0/1"].connect(core[f"g1/0/{2 + f}"])
    core.config(f"interface g1/0/{2 + f}\n switchport mode trunk")
    # each floor switch gets a management address in VLAN 99
    sw.config(
        f"interface g0/1\n switchport mode trunk\ninterface vlan 99\n ip address 10.30.99.{11 + f} 255.255.255.0\n"
        "ip default-gateway 10.30.99.1"
    )
    sw.add_vlan(99, "MGMT")
    members = [sw]
    for h, (name, kind, vid, n) in enumerate(hosts):
        make = {"pc": net.pc, "laptop": net.laptop, "printer": net.printer, "server": net.server}[kind]
        d = make(name, at=(x + 80 * h, 590))
        if n is None:
            d.use_dhcp()
        else:
            d.set_ip(f"10.30.{vid}.{n}/24", f"10.30.{vid}.1")
        sw[f"fa0/{h + 1}"].connect(d["fa0"])
        sw.config(f"interface fa0/{h + 1}\n switchport mode access\n switchport access vlan {vid}")
        members.append(d)
    vids = sorted({h[2] for h in hosts})
    for v in vids:
        sw.add_vlan(v, VLANS[v])  # named, as on the core
    net.around(*members, shape="rectangle", outline=COLOURS[floor], pad=35)
    net.note(f"{floor}\n" + ", ".join(VLANS[v] for v in vids), at=(x - 30, 370))

# --- the clinic, over serial ------------------------------------------------
clinic = net.router("CLINIC", "2911", at=(1850, 170))
clinic.add_module("HWIC-2T", slot=(0, 0))
edge["se0/0/0"].connect(clinic["se0/0/0"])  # EDGE is the DCE end
edge["se0/0/0"].address = "10.31.255.1/30"
clinic["se0/0/0"].address = "10.31.255.2/30"
csw = net.switch("CLINIC-SW", at=(1850, 300))
clinic["g0/0"].connect(csw["g0/1"])
csw.config("interface g0/1\n switchport mode trunk")
ccfg = ["interface g0/0", " no shutdown", "ip access-list extended ADMIN-IN", *ACLS["ADMIN-IN"]]
ccfg += ["router ospf 1", " router-id 10.31.254.1", " network 10.31.255.0 0.0.0.3 area 0"]
for vid in (10, 30):
    ccfg += [
        f"interface g0/0.{vid}",
        f" encapsulation dot1Q {vid}",
        f" ip address 10.31.{vid}.1 255.255.255.0",
        *([" ip access-group ADMIN-IN in"] if vid == 30 else []),
        f"ip dhcp excluded-address 10.31.{vid}.1 10.31.{vid}.9",
        f"ip dhcp pool CLINIC-{VLANS[vid]}",
        f" network 10.31.{vid}.0 255.255.255.0",
        f" default-router 10.31.{vid}.1",
        " dns-server 8.8.8.8",
        "router ospf 1",
        f" network 10.31.{vid}.0 0.0.0.255 area 0",
    ]
clinic.config(ccfg)
clinic_hosts = [("CLINIC-PC1", 10), ("CLINIC-PC2", 10), ("RECEPTION-PC", 30)]
for h, (name, vid) in enumerate(clinic_hosts):
    d = net.pc(name, at=(1750 + 100 * h, 430))
    d.use_dhcp()
    csw[f"fa0/{h + 1}"].connect(d["fa0"])
    csw.config(f"interface fa0/{h + 1}\n switchport mode access\n switchport access vlan {vid}")
    csw.add_vlan(vid, VLANS[vid])

# --- drawings ---------------------------------------------------------------
net.around(isp, inet, shape="rectangle", outline="grey", label="INTERNET", pad=40)
net.around(edge, core, shape="rectangle", outline="blue", label="HOSPITAL CORE: OSPF area 0", pad=30)
net.around(
    clinic,
    csw,
    *[name for name, _ in clinic_hosts],
    shape="rectangle",
    outline="teal",
    label="OUTPATIENT CLINIC: serial WAN",
    pad=40,
)
net.note(
    "MEDICAL devices talk to CLINICAL and RECORDS only.\nADMIN never reaches patient data. GUEST gets the internet.",
    at=(60, 80),
)

# --- ping checks ------------------------------------------------------------
net.ping("ED-PC1", "EHR", scenario="Clinical to patient records")
net.ping("WARD-PC1", "PACS", scenario="Clinical to patient records")
net.ping("CLINIC-PC1", "EHR", scenario="Clinical to patient records")
net.ping("MONITOR1", "PACS", scenario="Medical devices to records")
net.ping("PUMP1", "EHR", scenario="Medical devices to records")
net.ping("BILLING-PC1", "BILLING", scenario="Admin to admin servers")
net.ping("RECEPTION-PC", "MAIL", scenario="Admin to admin servers")
net.ping("HR-PC1", "INTERNET", scenario="Staff and guests to internet")
net.ping("ED-PC2", "INTERNET", scenario="Staff and guests to internet")
net.ping("VISITOR1", "INTERNET", scenario="Staff and guests to internet")
net.ping("BILLING-PC1", "EHR", scenario="Admin to patient records: should FAIL")
net.ping("RECEPTION-PC", "PACS", scenario="Admin to patient records: should FAIL")
net.ping("HR-PC1", "PUMP1", scenario="Admin to patient records: should FAIL")
net.ping("PUMP2", "INTERNET", scenario="Medical devices to internet: should FAIL")
net.ping("VISITOR1", "PUMP1", scenario="Guest to hospital: should FAIL")
net.ping("VISITOR2", "EHR", scenario="Guest to hospital: should FAIL")

net.save("hospital.pkt")
print(f"hospital.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
