"""rt07: home and ISP kit: home routers, cable, DSL, cellular, an 819 on serial.

Stresses: Linksys-WRT300N, DLC100 and HomeRouter-PT-AC (their GUI port names
with spaces); Cable-Modem-PT and DSL-Modem-PT with coax and phone cables; a
CoAxialSplitter feeding a TV; Central-Office-Server with a Cell-Tower on
coax; an 819HGW on its built-in Serial0 to a 2911 + HWIC-2T, doing NAT
overload for its own DHCP LAN; an ISP router handing out WAN addresses by
DHCP to the home routers; a 2811 + WIC-1ENET (Ethernet0/0/0, 10 Mb) port.
Cloud-PT (what PT uses to join modems to an ISP) is not a verified model,
so the modem paths are cabled as far as pktlib allows: see FINDINGS.

Check in Packet Tracer:
  - HOME1 (Linksys) GUI > Status: Internet IP from 100.100.1.0/24 (ISP DHCP);
    PC-H1A `ipconfig` shows 192.168.0.x and `ping 9.9.9.9` works through
    the Linksys NAT
  - HOME2 (HomeRouter-PT-AC) and HOME3 (DLC100) WAN state: they sit behind
    the cable and DSL modems; expected NOT to get an address (no Cloud-PT)
  - cable colours: coax grey on modem/splitter/tower links, phone pink on DSL
  - SOHO (819HGW) `show ip nat translations` after PC-SOHO `ping 9.9.9.9`
  - ISP `show ip dhcp binding`: HOME1 (and the 819 if it took DHCP)
  - CO-SERVER and CELL-TOWER: coax link green; the CO server's Backbone IP
    is whatever its GUI says (pktlib could only write IOS text for it)
"""

from _common import attempt, finish, note, pktlib, wire

net = pktlib.new()

isp = net.router("ISP", "2911", at=(600, 120))
attempt("ISP HWIC-2T", isp.add_module, "HWIC-2T")
attempt("ISP HWIC-4ESW", isp.add_module, "HWIC-4ESW", slot=(0, 1))
legacy = net.router("LEGACY", "2811", at=(900, 120))
attempt("LEGACY WIC-1ENET", legacy.add_module, "WIC-1ENET")
srv = net.server("NINES", at=(600, -20), ip="9.9.9.9/24", gateway="9.9.9.1")
isp["g0/2"].connect(srv["fa0"])
isp["g0/2"].address = "9.9.9.1/24"

# a 10 Mb Ethernet WIC to show a third port family on the same router
attempt("LEGACY Ethernet0/0/0 to ISP fa0/1/0 (HWIC-4ESW switch port)", lambda: legacy["e0/0/0"].connect(isp["fa0/1/0"]))
legacy["e0/0/0"].address = "100.100.9.2/24"
isp.config("interface Vlan1\n ip address 100.100.9.1 255.255.255.0\n no shutdown")
legacy.config("ip route 0.0.0.0 0.0.0.0 100.100.9.1")

# --- HOME1: Linksys straight onto the ISP, WAN by DHCP -----------------------
home1 = net.add_device("HOME1", "Linksys-WRT300N", at=(250, 300))
attempt("HOME1 Internet to ISP g0/0", lambda: home1["Internet"].connect(isp["g0/0"]))
isp["g0/0"].address = "100.100.1.1/24"
isp.config("""
ip dhcp excluded-address 100.100.1.1 100.100.1.9
ip dhcp pool HOME-WAN
 network 100.100.1.0 255.255.255.0
 default-router 100.100.1.1
 dns-server 9.9.9.9
""")
for i, (name, make) in enumerate((("PC-H1A", net.pc), ("PC-H1B", net.pc), ("LAPTOP-H1", net.laptop))):
    d = make(name, at=(120 + 110 * i, 440))
    d.use_dhcp()
    attempt(f"{name} to HOME1 Ethernet {i + 1}", lambda d=d, i=i: home1[f"Ethernet {i + 1}"].connect(d["fa0"]))
# the natural thing for a home router's LAN: change its address. pktlib accepts it,
# but writes IOS lines into a device that has no IOS (has_ios is True for it)
print("HOME1 has_ios:", home1.has_ios, "running_config before:", home1.running_config)
attempt("HOME1 LAN address", setattr, home1["Ethernet 1"], "address", "192.168.50.1/24")
print("HOME1 running_config after:", home1.running_config, "| Ethernet 1 address reads", home1["Ethernet 1"].address)
if home1.running_config:
    note(
        "Linksys-WRT300N/DLC100/HomeRouter-PT-AC/Central-Office-Server report has_ios=True (empty RUNNINGCONFIG); "
        "Port.address / set_ip / config() write IOS text into them that PT's GUI config ignores; "
        "no API for a home router's LAN IP, DHCP range, WAN mode or SSID"
    )
    home1.running_config = []  # put it back so this file tests the defaults (192.168.0.1, DHCP on)

# --- cellular: central office and a tower ----------------------------------
co = net.add_device("CO-SERVER", "Central-Office-Server", at=(250, 120))
tower = net.add_device("CELL-TOWER", "Cell-Tower", at=(100, 120))
attempt("tower to CO coax", lambda: tower["Coaxial0"].connect(co["Coaxial0/0"]))
attempt("CO Backbone to ISP g0/1", lambda: co["Backbone"].connect(isp["g0/1"]))
isp["g0/1"].address = "100.100.2.1/24"
attempt("CO-SERVER Backbone address", co.set_ip, "100.100.2.2", 24, "100.100.2.1", port="Backbone")
print("CO-SERVER running_config:", co.running_config)
attempt("Smartphone-PT for the tower", net.add_device, "MOBILE", "SMARTPHONE-PT", at=(100, 250))
attempt("CO Cellular0/0 cable (untyped port, should refuse)", lambda: co["Cellular0/0"].connect(tower["3G/4G Server1"]))

# --- HOME2: cable ------------------------------------------------------------
home2 = net.add_device("HOME2", "HomeRouter-PT-AC", at=(600, 450))
cmodem = net.add_device("CABLE-MODEM", "Cable-Modem-PT", at=(600, 330))
attempt("HOME2 Internet to cable modem Port 1", lambda: home2["Internet"].connect(cmodem["Port 1"]))
pc2 = net.pc("PC-H2", at=(600, 580))
pc2.use_dhcp()
attempt("PC-H2 to HOME2 GigabitEthernet 1", lambda: home2["GigabitEthernet 1"].connect(pc2["fa0"]))
cloud = attempt("Cloud-PT (the cable/DSL head end)", net.add_device, "CLOUD", "Cloud-PT", at=(800, 300))
splitter = net.add_device("SPLITTER", "CoAxialSplitter-PT", at=(750, 400))
tv = net.add_device("TV", "TV-PT", at=(850, 470))
attempt("cable modem Port 0 to splitter (coax)", lambda: cmodem["Port 0"].connect(splitter["Coaxial0"]))
attempt("splitter to TV (coax)", lambda: splitter["Coaxial1"].connect(tv["Port 0"]))
attempt(
    "straight cable on a coax port (should refuse)",
    lambda: splitter["Coaxial2"].connect(co["Coaxial0/1"], cable="straight"),
)

# --- HOME3: DSL -------------------------------------------------------------
home3 = net.add_device("HOME3", "DLC100", at=(950, 450))
dsl = net.add_device("DSL-MODEM", "DSL-Modem-PT", at=(950, 330))
attempt("HOME3 Internet to DSL modem Port 1", lambda: home3["Internet"].connect(dsl["Port 1"]))
pc3 = net.laptop("LAPTOP-H3", at=(950, 580))
pc3.use_dhcp()
attempt("LAPTOP-H3 to HOME3 Ethernet 1", lambda: home3["Ethernet 1"].connect(pc3["fa0"]))
phone = net.add_device("LANDLINE", "Analog-Phone-PT", at=(1100, 330))
# without Cloud-PT the only other phone port is an analogue phone: cable it to show the phone cable
link = attempt("DSL modem Port 0 to analogue phone (phone cable)", lambda: dsl["Port 0"].connect(phone["Port 0"]))
if link:
    print("DSL line cable:", link.cable)
spare = net.pc("PC-SPARE", at=(1100, 580))
attempt(
    "phone cable on Ethernet ports (should refuse)", lambda: home3["Ethernet 2"].connect(spare["fa0"], cable="phone")
)

# --- SOHO: 819HGW on built-in serial, NAT for its own LAN ---------------------
soho = net.router("SOHO", "819HGW", at=(250, 600))
attempt(
    "ISP se0/0/0 (smart serial) to SOHO Serial0 (plain serial)", wire, isp, "se0/0/0", soho, "Serial0", "100.100.3.0/30"
)
soho.config("""
interface Serial0
 ip nat outside
interface Vlan1
 ip nat inside
ip access-list standard SOHO-LAN
 permit 10.10.10.0 0.0.0.7
ip nat inside source list SOHO-LAN interface Serial0 overload
ip dhcp pool ccp-pool
 dns-server 9.9.9.9
ip route 0.0.0.0 0.0.0.0 100.100.3.1
""")
pc_soho = net.pc("PC-SOHO", at=(250, 720))
pc_soho.use_dhcp()
attempt("PC-SOHO to SOHO FastEthernet0 (switch port)", lambda: soho["fa0"].connect(pc_soho["fa0"]))
print(
    "SOHO dhcp pool block:",
    [l for l in soho.running_config if "ccp-pool" in l or l.startswith((" network", " dns", " default-router"))],
)

# ISP: one default for everything back home is not needed (all connected), routes for LEGACY's peers are
isp.config("router ospf 1\n network 100.100.0.0 0.0.255.255 area 0\n network 9.9.9.0 0.0.0.255 area 0")

for l in net.links:
    (a, ap), (b, bp) = l.ends
    print(f"  {a}.{ap} <-{l.cable}-> {b}.{bp}")
net.around(home1, "PC-H1A", "PC-H1B", "LAPTOP-H1", shape="ellipse", outline="green", label="HOME1 Linksys")
net.around(home2, cmodem, pc2, splitter, tv, shape="ellipse", outline="orange", label="HOME2 cable")
net.around(home3, dsl, pc3, phone, shape="ellipse", outline="blue", label="HOME3 DSL")
net.around(co, tower, shape="ellipse", outline="grey", label="CELLULAR")
finish(net, "rt07_home_isp")
