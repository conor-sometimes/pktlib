"""Stress: 24 IP phones with a PC behind each, CME, PoE, port security, DHCP snooping.

CME (2811) is the gateway, DHCP server and call manager in one: router-on-a-stick on
fa0/0 (fa0/0.100 DATA, fa0/0.110 VOICE), a DHCP pool for each (VOICE with option 150),
telephony-service with 24 ephone-dns (extensions 3001-3024, auto assign).

ACC-POE (3560-24PS, PoE) has 20 phones on fa0/1-20, each port with
  access VLAN 100, voice VLAN 110, `power inline auto`, `mls qos trust device cisco-phone`,
  port security (maximum 3, sticky, violation restrict), portfast.
ACC-2960 (2960-24TT, no PoE) has 4 phones on fa0/1-4 with power adapters, same port config
minus the PoE and QoS lines. ACC-2960 is daisy-chained off ACC-POE's g0/2.
Both switches run `cdp run` (phones learn the voice VLAN over CDP) and DHCP snooping on
100 and 110, with `no ip dhcp snooping information option` and only the uplink trusted.
VLANs 100 and 110 are given ONLY through `switchport access vlan 100` and
`switchport voice vlan 110`; the script reports whether VLAN 110 ended up in the VLAN
database (IOS creates a voice VLAN that doesn't exist).

Check in Packet Tracer:
  CME# show ephone              -> 24 phones REGISTERED, DNs 3001-3024
  PHONE1 screen shows extension 3001 (all 24 phones should show a number)
  DESK1 (PC behind PHONE1) DHCP -> 10.50.100.x, ping 10.50.110.1
  ACC-POE# show power inline    -> 20 ports delivering power
  ACC-POE# show port-security   -> 20 ports, MaxSecureAddr 3, Action Restrict
  ACC-POE# show ip dhcp snooping binding -> bindings for phones and PCs
  ACC-POE# show vlan brief      -> VLAN 110 present (if it is missing, phones never get a voice address)
"""

from pathlib import Path

import pktlib

HERE = Path(__file__).resolve().parent
OUT = HERE / "sw05_voice_poe_security.pkt"
DATA, VOICE = 100, 110
CME_IP = "10.50.110.1"
PHONES_POE, PHONES_PLAIN = 20, 4
TOTAL = PHONES_POE + PHONES_PLAIN
problems: list[str] = []

net = pktlib.new()
cme = net.router("CME", "2811", at=(600, 60))
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
ip dhcp excluded-address 10.50.100.1 10.50.100.9
ip dhcp excluded-address 10.50.110.1 10.50.110.9
ip dhcp pool DATA
 network 10.50.100.0 255.255.255.0
 default-router 10.50.100.1
ip dhcp pool VOICE
 network 10.50.110.0 255.255.255.0
 default-router {CME_IP}
 option 150 ip {CME_IP}
telephony-service
 max-ephones {TOTAL}
 max-dn {TOTAL}
 ip source-address {CME_IP} port 2000
 auto assign 1 to {TOTAL}
"""
    + "".join(f"ephone-dn {d}\n number {3000 + d}\n" for d in range(1, TOTAL + 1))
)

snoop = f"""
cdp run
ip dhcp snooping
ip dhcp snooping vlan {DATA},{VOICE}
no ip dhcp snooping information option
"""
poe = net.multilayer("ACC-POE", "3560-24PS", at=(600, 220))
plain = net.switch("ACC-2960", "2960-24TT", at=(1500, 220))
poe.config(
    snoop
    + """
interface g0/1
 switchport trunk encapsulation dot1q
 switchport mode trunk
 ip dhcp snooping trust
interface g0/2
 switchport trunk encapsulation dot1q
 switchport mode trunk
"""
)
plain.config(snoop + "interface g0/1\n switchport mode trunk\n ip dhcp snooping trust")
cme["fa0/0"].connect(poe["g0/1"])
poe["g0/2"].connect(plain["g0/1"])

n = 0
for sw, count, has_poe, x0 in ((poe, PHONES_POE, True, 60), (plain, PHONES_PLAIN, False, 1350)):
    for i in range(count):
        n += 1
        x, y = x0 + (i % 10) * 105, 380 + (i // 10) * 220
        phone = net.phone(f"PHONE{n}", at=(x, y), power_adapter=not has_poe)
        desk = net.pc(f"DESK{n}", at=(x, y + 100))
        desk.use_dhcp()
        sw[f"fa0/{i + 1}"].connect(phone["Switch"])
        phone["PC"].connect(desk["fa0"])
        lines = [
            f"interface fa0/{i + 1}",
            " switchport mode access",
            f" switchport access vlan {DATA}",
            f" switchport voice vlan {VOICE}",
            " switchport port-security",
            " switchport port-security maximum 3",
            " switchport port-security mac-address sticky",
            " switchport port-security violation restrict",
            " spanning-tree portfast",
        ]
        if has_poe:
            lines += [" power inline auto", " mls qos trust device cisco-phone"]
        sw.config(lines)

for sw in (poe, plain):
    if VOICE not in sw.vlans:
        problems.append(
            f"{sw.name}: `switchport voice vlan {VOICE}` did not create VLAN {VOICE} in the "
            f"VLAN database (has {sorted(v for v in sw.vlans if v < 1000)})"
        )

net.around(cme, poe, label="CME + PoE + snooping", outline="orange", pad=40)
net.save(OUT)
for p in problems:
    print("  finding:", p)
print(f"{OUT.name}: {len(net.devices)} devices, {len(net.links)} links")
