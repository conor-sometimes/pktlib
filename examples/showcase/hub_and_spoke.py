"""A hub-and-spoke WAN: six branch offices on serial links to one head office hub, EIGRP over all of it.

    uv run python examples/showcase/hub_and_spoke.py        # writes hub_and_spoke.pkt

hub        a 2911 with three HWIC-2T cards (six serial ports), the DCE end of
           every branch link; NAT overload to the ISP for everyone, and the
           default route redistributed into EIGRP 100
head office  the HQ servers (ERP, FILES, PAYMENTS) on 10.0.10.0/24
branches   an 1841 with a WIC-2T each, router on a stick with two VLANs:
             STAFF   10.<n>.10.0/24, DHCP from the branch router
             TILLS   10.<n>.20.0/24, the shop tills, which may only reach
                     the PAYMENTS server (an ACL on the sub-interface)
           Branch to branch traffic goes through the hub.

Change BRANCHES and run it again (up to six: one per serial port on the hub).

Check in Packet Tracer:
  HUB# show ip eigrp neighbors         -> six neighbours, one per serial
  LIMERICK# show ip route eigrp        -> D routes to every other branch, D*EX default
  HUB# show ip nat translations        -> entries on 203.0.113.2 after the internet pings
  LIMERICK-PC ping 10.0.10.20 (FILES)  -> success
  LIMERICK-TILL ping 10.0.10.30 (PAYMENTS) works; ping 8.8.8.8 fails
  SLIGO-PC ping 10.6.10.1 (DUNDALK's gateway) -> spoke to spoke, through the hub
  Or click the ping scenarios under the workspace.
"""

import pktlib

BRANCHES = ["LIMERICK", "WATERFORD", "KILKENNY", "SLIGO", "ATHLONE", "DUNDALK"]
HUB_SERIALS = ["se0/0/0", "se0/0/1", "se0/1/0", "se0/1/1", "se0/2/0", "se0/2/1"]
HQ_SERVERS = {"ERP": 10, "FILES": 20, "PAYMENTS": 30}
PAYMENTS = "10.0.10.30"
EIGRP_METRIC = "1544 2000 255 1 1500"
HX, HY = 830, 300  # the hub; branches sit in a row below it, 270 apart

net = pktlib.new()

# --- head office -------------------------------------------------------------
hub = net.router("HUB", "2911", at=(HX, HY))
for slot in range(3):
    hub.add_module("HWIC-2T", slot=(0, slot))
isp = net.router("ISP", "2911", at=(HX + 300, 60))
inet = net.server("INTERNET", at=(HX + 550, 60), ip="8.8.8.8/24", gateway="8.8.8.1")
isp["g0/1"].connect(inet["fa0"])
isp["g0/1"].address = "8.8.8.1/24"
isp["g0/0"].connect(hub["g0/1"])
isp["g0/0"].address = "203.0.113.1/30"
isp.config("ip route 203.0.113.0 255.255.255.0 203.0.113.2")  # the company's public block
hub["g0/1"].address = "203.0.113.2/30"
hub["g0/0"].address = "10.0.10.1/24"

hq_sw = net.switch("HQ-SW", at=(HX - 350, 60))
hub["g0/0"].connect(hq_sw["g0/1"])
servers = []
for i, (name, host) in enumerate(HQ_SERVERS.items()):
    s = net.server(name, at=(HX - 550 + 120 * i, 180), ip=f"10.0.10.{host}/24", gateway="10.0.10.1")
    hq_sw[f"fa0/{i + 1}"].connect(s["fa0"])
    servers.append(s)

hub.config(f"""
interface g0/1
 ip nat outside
interface g0/0
 ip nat inside
access-list 1 permit 10.0.0.0 0.255.255.255
ip nat inside source list 1 interface GigabitEthernet0/1 overload
ip route 0.0.0.0 0.0.0.0 203.0.113.1
router eigrp 100
 no auto-summary
 network 10.0.10.0 0.0.0.255
 redistribute static metric {EIGRP_METRIC}
""")

# --- branches -----------------------------------------------------------------
TILLS_IN = [
    "ip access-list extended TILLS-IN",
    " permit udp any any eq 67",  # DHCP from the branch router
    f" permit ip any host {PAYMENTS}",
    " deny ip any any",
]
for n, name in enumerate(BRANCHES, 1):
    x = HX + 270 * (n - 1 - (len(BRANCHES) - 1) / 2)
    br = net.router(name, "1841+WIC-2T", at=(x, 520))
    port = HUB_SERIALS[n - 1]
    hub[port].connect(br["se0/0/0"])  # the hub is the DCE end
    hub[port].address = f"172.16.{n}.1/30"
    br["se0/0/0"].address = f"172.16.{n}.2/30"
    hub.config(f"interface {port}\n ip nat inside\nrouter eigrp 100\n network 172.16.{n}.0 0.0.0.3")

    cfg = ["interface fa0/0", " no shutdown", *TILLS_IN]
    for vid, vname in ((10, "STAFF"), (20, "TILLS")):
        cfg += [
            f"interface fa0/0.{vid}",
            f" encapsulation dot1Q {vid}",
            f" ip address 10.{n}.{vid}.1 255.255.255.0",
            *([" ip access-group TILLS-IN in"] if vname == "TILLS" else []),
            f"ip dhcp excluded-address 10.{n}.{vid}.1 10.{n}.{vid}.9",
            f"ip dhcp pool {vname}",
            f" network 10.{n}.{vid}.0 255.255.255.0",
            f" default-router 10.{n}.{vid}.1",
            " dns-server 8.8.8.8",
        ]
    cfg += [
        "router eigrp 100",
        " no auto-summary",
        f" network 172.16.{n}.0 0.0.0.3",
        f" network 10.{n}.10.0 0.0.0.255",
        f" network 10.{n}.20.0 0.0.0.255",
    ]
    br.config(cfg)

    sw = net.switch(f"{name}-SW", at=(x, 650))
    br["fa0/0"].connect(sw["g0/1"])
    sw.config("interface g0/1\n switchport mode trunk")
    site = [br, sw]
    for k, (hname, vid) in enumerate(((f"{name}-PC", 10), (f"{name}-TILL", 20))):
        d = net.pc(hname, at=(x - 60 + 120 * k, 780))
        d.use_dhcp()
        sw[f"fa0/{k + 1}"].connect(d["fa0"])
        sw.config(f"interface fa0/{k + 1}\n switchport mode access\n switchport access vlan {vid}")
        site.append(d)
    net.around(*site, shape="rectangle", outline="green", pad=30)
    net.note(f"{name}\n10.{n}.0.0/16", at=(x - 80, 450))

# --- drawings -----------------------------------------------------------------
net.around(hub, hq_sw, *servers, shape="rectangle", outline="blue", label="HEAD OFFICE: 10.0.10.0/24", pad=40)
net.around(isp, inet, shape="rectangle", outline="grey", label="INTERNET", pad=40)
net.note(
    "Every spoke: serial to the HUB (DCE), EIGRP 100.\nTILLS VLAN 20 reaches PAYMENTS and nothing else.",
    at=(1100, 220),
)

# --- ping checks --------------------------------------------------------------
first, last = BRANCHES[0], BRANCHES[-1]
for name in BRANCHES:
    net.ping(f"{name}-PC", "FILES", scenario="Branches to HQ servers")
net.ping(f"{first}-TILL", "PAYMENTS", scenario="Tills to payments")
net.ping(f"{last}-TILL", "PAYMENTS", scenario="Tills to payments")
net.ping(f"{first}-PC", "INTERNET", scenario="Branches to internet")
net.ping(f"{last}-PC", "INTERNET", scenario="Branches to internet")
net.ping(f"{first}-PC", f"{last}-PC", ip=f"10.{len(BRANCHES)}.10.1", scenario="Spoke to spoke through the hub")
net.ping(f"{last}-PC", f"{first}-PC", ip="10.1.10.1", scenario="Spoke to spoke through the hub")
net.ping(f"{first}-TILL", "INTERNET", scenario="Tills to anything but payments: should FAIL")
net.ping(f"{first}-TILL", "FILES", scenario="Tills to anything but payments: should FAIL")

net.save("hub_and_spoke.pkt")
print(f"hub_and_spoke.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
