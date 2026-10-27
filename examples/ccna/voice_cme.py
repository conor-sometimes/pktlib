"""IP phones on a voice VLAN: a PoE switch, PCs behind the phones, and a router running CME.

    uv run python examples/ccna/voice_cme.py        # writes voice_cme.pkt

Four 7960 IP phones each share a switch port with a PC plugged into the
phone's own PC port. The port carries two VLANs: the PC's data untagged in the
access VLAN (100 DATA) and the phone's traffic tagged in the voice VLAN
(`switchport voice vlan 110`). The phone learns the voice VLAN from the
switch over CDP, hence `cdp run` (Packet Tracer ships the 3560 with CDP off).
The 3560-24PS powers the phones over the cable (PoE), so no power adapters.

CME, a 2811, does everything else from a trunk to the switch:

  - router on a stick: Fa0/0.100 (10.50.100.1) and Fa0/0.110 (10.50.110.1)
  - DHCP pools for both VLANs; the VOICE pool has `option 150`, the TFTP
    server the phones fetch their settings from (CME itself)
  - `telephony-service`: up to 4 phones, `ip source-address` where they
    register, `auto assign` giving extensions 1001 to 1004 (`ephone-dn`)

Check in Packet Tracer (give the phones a minute to boot and register):
  - CME `show ephone`: four phones, each REGISTERED with an IP in 10.50.110.0/24
  - each phone's screen shows its extension, 1001 to 1004; dial 1002 from
    PHONE1 and PHONE2 rings
  - DESK1 Desktop > IP Configuration: DHCP address in 10.50.100.0/24
  - SW1 `show interfaces fa0/1 switchport`: access VLAN 100, voice VLAN 110
  - SW1 `show power inline`: power on Fa0/1 to Fa0/4
"""

import pktlib

PHONES = 4
DATA, VOICE = 100, 110
CME_IP = "10.50.110.1"

net = pktlib.new()
cme = net.router("CME", "2811", at=(500, 60))
sw = net.multilayer("SW1", "3560-24PS", at=(500, 220))
cme["fa0/0"].connect(sw["g0/1"])
server = net.server("SERVER", at=(820, 220), ip="10.50.100.5/24", gateway="10.50.100.1")
sw["fa0/24"].connect(server["fa0"])

sw.add_vlan(DATA, "DATA")
sw.add_vlan(VOICE, "VOICE")
sw.config(f"""
cdp run
interface g0/1
 switchport trunk encapsulation dot1q
 switchport mode trunk
interface fa0/24
 switchport mode access
 switchport access vlan {DATA}
""")
for p in range(1, PHONES + 1):
    x = 200 + 200 * (p - 1)
    phone = net.phone(f"PHONE{p}", at=(x, 380))
    desk = net.pc(f"DESK{p}", at=(x, 520))
    desk.use_dhcp()
    sw[f"fa0/{p}"].connect(phone["Switch"])
    phone["PC"].connect(desk["fa0"])
    sw.config(f"""
interface fa0/{p}
 switchport mode access
 switchport access vlan {DATA}
 switchport voice vlan {VOICE}
 spanning-tree portfast
""")

cme.config(
    f"""
interface fa0/0
 no shutdown
interface fa0/0.{DATA}
 encapsulation dot1Q {DATA}
 ip address 10.50.100.1 255.255.255.0
interface fa0/0.{VOICE}
 encapsulation dot1Q {VOICE}
 ip address {CME_IP} 255.255.255.0
ip dhcp excluded-address 10.50.100.1 10.50.100.10
ip dhcp excluded-address 10.50.110.1 10.50.110.10
ip dhcp pool DATA
 network 10.50.100.0 255.255.255.0
 default-router 10.50.100.1
ip dhcp pool VOICE
 network 10.50.110.0 255.255.255.0
 default-router {CME_IP}
 option 150 ip {CME_IP}
telephony-service
 max-ephones {PHONES}
 max-dn {PHONES}
 ip source-address {CME_IP} port 2000
 auto assign 1 to {PHONES}
"""
    + "".join(f"ephone-dn {d}\n number {1000 + d}\n" for d in range(1, PHONES + 1))
)

net.around(
    *[f"PHONE{p}" for p in range(1, PHONES + 1)],
    shape="rectangle",
    outline="orange",
    label="VLAN 110 VOICE: 1001 to 1004",
    pad=30,
)
net.around(
    *[f"DESK{p}" for p in range(1, PHONES + 1)],
    shape="rectangle",
    outline="blue",
    label="VLAN 100 DATA (behind the phones)",
    pad=30,
)
net.note("telephony-service\nDHCP, option 150", at=(600, 20))

net.ping("DESK1", "SERVER", scenario="Desk PC through its phone to the server")
net.ping("DESK3", "CME", ip=CME_IP, scenario="Data VLAN to the voice VLAN gateway")
net.ping("DESK4", "SERVER", scenario="Desk PC through its phone to the server")

net.save("voice_cme.pkt")
print(f"voice_cme.pkt: {len(net.devices)} devices, {len(net.links)} links")
