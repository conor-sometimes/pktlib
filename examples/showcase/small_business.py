"""A small business with IP phones: one router does routing, DHCP, NAT and call control (CME).

    uv run python examples/showcase/small_business.py       # writes small_business.pkt

router     a 2811 called GATEWAY: router on a stick for three VLANs, a DHCP
           pool for each, NAT overload to the ISP, and telephony-service so
           the phones register and get extensions 101 upwards
switch     a PoE 3560 (the phones take their power from it) with `cdp run`,
           since the phones learn their voice VLAN over CDP
desks      an IP phone on each desk with the PC plugged into the phone:
           the PC is in DATA (VLAN 10), the phone in VOICE (VLAN 20)
also       a NAS and a printer on fixed addresses, and a lobby port in
           GUEST (VLAN 30) that only reaches the internet

Change PHONES and run it again; extensions and switch ports follow.

Check in Packet Tracer:
  GATEWAY# show ephone                 -> every phone REGISTERED
  PHONE1 (GUI tab)                     -> shows extension 101; dial 102 and PHONE2 rings
  GATEWAY# show ip dhcp binding        -> leases in 192.168.10.x and 192.168.20.x
  GATEWAY# show ip nat translations    -> entries on 203.0.113.2 after the internet pings
  DESK1 ping 192.168.10.5 (NAS) works; LOBBY ping 192.168.10.5 fails
  Or click the ping scenarios under the workspace.
"""

import pktlib

PHONES = 6
VLANS = {10: "DATA", 20: "VOICE", 30: "GUEST"}
CME = "192.168.20.1"

net = pktlib.new()

# --- the internet --------------------------------------------------------------
isp = net.router("ISP", "2911", at=(700, 40))
inet = net.server("INTERNET", at=(950, 40), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].address = "203.0.113.1/30"
isp.config("ip route 203.0.113.0 255.255.255.0 203.0.113.2")  # the business's public block

# --- the gateway: everything in one 2811 ----------------------------------------
gw = net.router("GATEWAY", "2811", at=(700, 170))
gw["fa0/1"].connect(isp["g0/0"])
gw["fa0/1"].address = "203.0.113.2/30"
cfg = [
    "interface fa0/0",
    " no shutdown",
    "interface fa0/1",
    " ip nat outside",
    "ip access-list extended GUEST-IN",
    " permit udp any any eq 67",
    " deny ip any 192.168.0.0 0.0.255.255",
    " permit ip any any",
    "access-list 1 permit 192.168.0.0 0.0.255.255",
    "ip nat inside source list 1 interface FastEthernet0/1 overload",
    "ip route 0.0.0.0 0.0.0.0 203.0.113.1",
]
for vid, name in VLANS.items():
    cfg += [
        f"interface fa0/0.{vid}",
        f" encapsulation dot1Q {vid}",
        f" ip address 192.168.{vid}.1 255.255.255.0",
        " ip nat inside",
        *([" ip access-group GUEST-IN in"] if name == "GUEST" else []),
        f"ip dhcp excluded-address 192.168.{vid}.1 192.168.{vid}.9",
        f"ip dhcp pool {name}",
        f" network 192.168.{vid}.0 255.255.255.0",
        f" default-router 192.168.{vid}.1",
        # phones fetch their settings from the TFTP server option 150 names: the CME
        f" option 150 ip {CME}" if name == "VOICE" else " dns-server 8.8.8.8",
    ]
cfg += [
    "telephony-service",
    f" max-ephones {PHONES}",
    f" max-dn {PHONES}",
    f" ip source-address {CME} port 2000",
    f" auto assign 1 to {PHONES}",
]
for d in range(1, PHONES + 1):
    cfg += [f"ephone-dn {d}", f" number {100 + d}"]
gw.config(cfg)

# --- the office switch ------------------------------------------------------------
sw = net.multilayer("OFFICE-SW", "3560-24PS", at=(700, 300))  # PoE
gw["fa0/0"].connect(sw["g0/1"])
sw.config("cdp run\ninterface g0/1\n switchport trunk encapsulation dot1q\n switchport mode trunk")
for vid, name in VLANS.items():
    sw.add_vlan(vid, name)

desks = []
for p in range(PHONES):
    x = 300 + 160 * p
    phone = net.phone(f"PHONE{p + 1}", at=(x, 440))
    desk = net.pc(f"DESK{p + 1}", at=(x, 560))
    desk.use_dhcp()
    sw[f"fa0/{p + 1}"].connect(phone["Switch"])
    phone["PC"].connect(desk["fa0"])
    sw.config(
        f"interface fa0/{p + 1}\n switchport mode access\n switchport access vlan 10\n"
        " switchport voice vlan 20\n spanning-tree portfast"
    )
    desks += [phone, desk]

nas = net.server("NAS", at=(1300, 300), ip="192.168.10.5/24", gateway="192.168.10.1")
printer = net.printer("PRINTER", at=(1300, 400), ip="192.168.10.6/24", gateway="192.168.10.1")
lobby = net.laptop("LOBBY", at=(150, 300))
lobby.use_dhcp()
for port, dev, vid in (("fa0/20", nas, 10), ("fa0/21", printer, 10), ("fa0/24", lobby, 30)):
    sw[port].connect(dev["fa0"])
    sw.config(f"interface {port}\n switchport mode access\n switchport access vlan {vid}\n spanning-tree portfast")

# --- drawings -------------------------------------------------------------------
net.around(isp, inet, shape="rectangle", outline="grey", label="INTERNET", pad=40)
net.around(*desks, shape="rectangle", outline="blue", pad=35)
net.note(f"DESKS: phones x101-{100 + PHONES}, a PC behind each", at=(270, 680))
net.around(nas, printer, shape="rectangle", outline="green", label="DATA VLAN 10", pad=35)
net.around(lobby, shape="ellipse", outline="orange", pad=40)
net.note("LOBBY: GUEST VLAN 30,\ninternet only", at=(90, 210))
net.note(
    "GATEWAY (2811): routing, DHCP, NAT and CME.\nDATA 192.168.10.0/24, VOICE .20, GUEST .30",
    at=(950, 160),
)

# --- ping checks ------------------------------------------------------------------
net.ping("DESK1", "NAS", scenario="Desks to NAS and printer")
net.ping(f"DESK{PHONES}", "PRINTER", scenario="Desks to NAS and printer")
net.ping("DESK1", "INTERNET", scenario="Office to internet")
net.ping("NAS", "INTERNET", scenario="Office to internet")
net.ping("LOBBY", "INTERNET", scenario="Guest to internet")
net.ping("LOBBY", "NAS", scenario="Guest to office: should FAIL")
net.ping("LOBBY", "PRINTER", scenario="Guest to office: should FAIL")

net.save("small_business.pkt")
print(f"small_business.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
