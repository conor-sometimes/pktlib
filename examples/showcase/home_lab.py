"""A home lab: the family network on a Linksys, and a study rack behind its own router.

    uv run python examples/showcase/home_lab.py             # writes home_lab.pkt

isp        a 2911 standing in for the broadband provider: it hands the home
           router its WAN address by DHCP and reaches a server on 8.8.8.8
home       a Linksys WRT300N on its factory settings (LAN 192.168.0.1/24,
           DHCP on, NAT to the WAN). The family PC, laptop and printer use it.
           pktlib doesn't write config into home routers: Packet Tracer
           ignores IOS there, so the defaults are what you get.
lab rack   LAB-RTR (2911) on the Linksys's fourth port with 192.168.0.2,
           NATting the lab onto that address, so the Linksys needs no routes;
           a 3560 with two VLANs (SERVERS, PRACTICE) routed on a stick; and a
           CCNA practice pod: two 1841s on a serial link running OSPF with
           LAB-RTR, each with a PC
           The family can't reach into the lab (no route through the Linksys);
           the lab can reach the family and the internet.

Check in Packet Tracer:
  HOME-ROUTER (GUI tab, Status)        -> an Internet address from 100.100.1.0/24
  FAMILY-PC Desktop > IP Configuration -> 192.168.0.x by DHCP; ping 8.8.8.8 works
  LAB-RTR# show ip ospf neighbor       -> POD-R1 FULL
  LAB-RTR# show ip nat translations    -> entries on 192.168.0.2 after NAS pings 8.8.8.8
  POD-PC2 ping 8.8.8.8                 -> through the pod, LAB-RTR's NAT, then the Linksys
  FAMILY-PC ping 10.10.10.10 (NAS)     -> fails, as it should
  Or click the ping scenarios under the workspace.
"""

import pktlib

net = pktlib.new()

# --- the broadband provider ----------------------------------------------------
isp = net.router("ISP", "2911", at=(400, 40))
inet = net.server("INTERNET", at=(650, 40), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].address = "100.100.1.1/24"
isp.config("""
ip dhcp excluded-address 100.100.1.1 100.100.1.9
ip dhcp pool HOMES
 network 100.100.1.0 255.255.255.0
 default-router 100.100.1.1
 dns-server 8.8.8.8
ip route 100.100.0.0 255.255.0.0 Null0
""")  # Null0: the provider's own block, as ISPs nail it down

# --- home ----------------------------------------------------------------------
home = net.add_device("HOME-ROUTER", "Linksys-WRT300N", at=(400, 200))
home["Internet"].connect(isp["g0/0"])
family = []
for i, (name, make) in enumerate((("FAMILY-PC", net.pc), ("FAMILY-LAPTOP", net.laptop)), 1):
    d = make(name, at=(140 + 130 * (i - 1), 340))
    d.use_dhcp()
    home[f"Ethernet {i}"].connect(d["fa0"])
    family.append(d)
# DHCP too: a fixed address with gateway 192.168.0.1 makes the audit complain, since
# that address is the Linksys's factory default and isn't written in the file
printer = net.printer("HOME-PRINTER", at=(400, 340))
printer.use_dhcp()
home["Ethernet 3"].connect(printer["fa0"])

# --- the lab rack ----------------------------------------------------------------
lab = net.router("LAB-RTR", "2911", at=(800, 200))
home["Ethernet 4"].connect(lab["g0/0"])
lab["g0/0"].address = "192.168.0.2/24"
lab["g0/2"].address = "10.10.255.1/30"
lab_cfg = [
    "interface g0/0",
    " ip nat outside",
    "interface g0/1",
    " no shutdown",
    "interface g0/2",
    " ip nat inside",
    "access-list 1 permit 10.10.0.0 0.0.255.255",
    "ip nat inside source list 1 interface GigabitEthernet0/0 overload",
    "ip route 0.0.0.0 0.0.0.0 192.168.0.1",
    "router ospf 1",
    " router-id 10.10.255.1",
    " network 10.10.255.0 0.0.0.3 area 0",
    " default-information originate",
]
for vid, name in ((10, "SERVERS"), (20, "PRACTICE")):
    lab_cfg += [
        f"interface g0/1.{vid}",
        f" description {name}",
        f" encapsulation dot1Q {vid}",
        f" ip address 10.10.{vid}.1 255.255.255.0",
        " ip nat inside",
        "router ospf 1",
        f" network 10.10.{vid}.0 0.0.0.255 area 0",
    ]
lab.config(lab_cfg)

lab_sw = net.multilayer("LAB-SW", "3560-24PS", at=(800, 330))
lab["g0/1"].connect(lab_sw["g0/1"])
lab_sw.config("interface g0/1\n switchport trunk encapsulation dot1q\n switchport mode trunk")
rack = [lab, lab_sw]
for i, (name, make, vid, host) in enumerate(
    (
        ("NAS", net.server, 10, 10),
        ("MEDIA-SERVER", net.server, 10, 11),
        ("STUDY-PC", net.pc, 20, 10),
        ("STUDY-LAPTOP", net.laptop, 20, 11),
    )
):
    d = make(name, at=(650 + 100 * i, 460), ip=f"10.10.{vid}.{host}/24", gateway=f"10.10.{vid}.1")
    lab_sw[f"fa0/{i + 1}"].connect(d["fa0"])
    lab_sw.config(f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {vid}")
    rack.append(d)

# the CCNA practice pod: two routers, a serial link, OSPF with LAB-RTR
pod = []
for n in (1, 2):
    r = net.router(f"POD-R{n}", "1841+WIC-2T", at=(1150, 120 + 200 * (n - 1)))
    pc = net.pc(f"POD-PC{n}", at=(1350, 120 + 200 * (n - 1)), ip=f"10.10.3{n}.10/24", gateway=f"10.10.3{n}.1")
    r["fa0/0"].connect(pc["fa0"])
    r["fa0/0"].address = f"10.10.3{n}.1/24"
    r.config(f"router ospf 1\n router-id 10.10.254.{n}\n network 10.10.3{n}.0 0.0.0.255 area 0")
    pod += [r, pc]
r1, r2 = pod[0], pod[2]
lab["g0/2"].connect(r1["fa0/1"])
r1["fa0/1"].address = "10.10.255.2/30"
r1["se0/0/0"].connect(r2["se0/0/0"])  # POD-R1 is the DCE end
r1["se0/0/0"].address = "10.10.255.5/30"
r2["se0/0/0"].address = "10.10.255.6/30"
r1.config("router ospf 1\n network 10.10.255.0 0.0.0.3 area 0\n network 10.10.255.4 0.0.0.3 area 0")
r2.config("router ospf 1\n network 10.10.255.4 0.0.0.3 area 0")

# --- drawings ---------------------------------------------------------------------
net.around(isp, inet, shape="rectangle", outline="grey", label="BROADBAND PROVIDER", pad=40)
net.around(home, *family, printer, shape="rectangle", outline="green", label="HOME: 192.168.0.0/24", pad=40)
net.around(*rack, shape="rectangle", outline="blue", label="LAB RACK: 10.10.0.0/16", pad=40)
net.around(*pod, shape="rectangle", outline="orange", label="CCNA POD: OSPF", pad=30)
net.note("Double NAT: the lab is NATted by LAB-RTR,\nthen again by the Linksys.", at=(950, 560))

# --- ping checks ------------------------------------------------------------------
net.ping("FAMILY-PC", "INTERNET", scenario="Home to internet")
net.ping("FAMILY-LAPTOP", "INTERNET", scenario="Home to internet")
net.ping("FAMILY-LAPTOP", "HOME-ROUTER", ip="192.168.0.1", scenario="Home to home router")
net.ping("NAS", "INTERNET", scenario="Lab to internet")
net.ping("POD-PC2", "INTERNET", scenario="Lab to internet")
net.ping("STUDY-PC", "HOME-ROUTER", ip="192.168.0.1", scenario="Lab to home router")
net.ping("POD-PC1", "NAS", scenario="Pod to lab servers")
net.ping("POD-PC2", "MEDIA-SERVER", scenario="Pod to lab servers")
net.ping("FAMILY-PC", "NAS", scenario="Home into the lab: should FAIL")

net.save("home_lab.pkt")
print(f"home_lab.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
