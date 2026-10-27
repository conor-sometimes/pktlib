"""rt04: every kind of NAT, ACLs on many interfaces, DHCP, floating statics.

Stresses, all on one ISR4331 (EDGE, NIM-2T fitted) and a 2911 (DIST):
  NAT      overload on the interface (named ACL), a pool for the server
           VLAN (numbered ACL), static one-to-one for MAIL, TCP and UDP port
           forwarding, and route-map NAT out of a second (serial) ISP
  ACLs     numbered extended in on a sub-interface, named extended in and out on
           two more, named extended in on both outside interfaces (using
           `established`), a standard ACL as a vty `access-class`
  DHCP     pools on EDGE reached through `ip helper-address` on DIST, a pool
           on DIST itself, excluded ranges
  routing  primary default tracked by IP SLA, floating static default (AD
           200) via the serial ISP; OSPF inside with `default-information
           originate`; a native-VLAN-99 trunk to a 2960

Check in Packet Tracer:
  - PC-STAFF1 / LAPTOP-GUEST / PC-LAB `ipconfig`: addresses from 10.10.10,
    10.10.20 and 10.10.40 (two pools via relay, one local)
  - PC-STAFF1 `ping 8.8.8.8`, then EDGE `show ip nat translations`: icmp
    entries on 203.0.113.2 (overload)
  - OUT-PC browser `http://203.0.113.80:8080` reaches WEB (port forward);
    OUT-PC `ping 203.0.113.25` reaches MAIL (static)
  - LAPTOP-GUEST `ping 10.20.30.80` fails (GUEST-OUT), `ping 8.8.8.8` works
  - EDGE `show ip sla statistics`, `show track`; shut g0/0/0 and the default
    moves to 198.51.100.1 (`show ip route static`)
  - EDGE `show access-lists`: match counts on every list
"""

from _common import attempt, finish, mask, nw, pktlib, plain, wire

net = pktlib.new()

edge = net.router("EDGE", "ISR4331", at=(600, 300))
attempt("EDGE NIM-2T", edge.add_module, "NIM-2T", slot=(0, 1))
dist = net.router("DIST", "2911", at=(600, 480))
isp_a = net.router("ISP-A", "2911", at=(400, 130))
isp_b = net.router("ISP-B", "2811", at=(800, 130))
attempt("ISP-B WIC-2T", isp_b.add_module, "WIC-2T")
inet = net.router("INET", "2911", at=(600, 20))

# --- outside ----------------------------------------------------------------
attempt("EDGE/ISP-A", wire, isp_a, "g0/0", edge, "g0/0/0", "203.0.113.0/29")
attempt("EDGE/ISP-B serial", wire, edge, "se0/1/0", isp_b, "se0/0/0", "198.51.100.0/30")
attempt("ISP-A/INET", wire, isp_a, "g0/1", inet, "g0/1", "100.64.0.0/30")
attempt("ISP-B/INET", wire, isp_b, "fa0/0", inet, "g0/2", "100.64.0.4/30")
inet_sw = net.switch("INET-SW", at=(850, 20))
inet["g0/0"].connect(inet_sw["fa0/1"])
inet["g0/0"].address = "8.8.8.1/24"
dns = net.server("DNS", at=(1000, -40), ip="8.8.8.8/24", gateway="8.8.8.1")
out_pc = net.pc("OUT-PC", at=(1000, 80), ip="8.8.8.100/24", gateway="8.8.8.1")
inet_sw["fa0/2"].connect(dns["fa0"])
inet_sw["fa0/3"].connect(out_pc["fa0"])
for r in (isp_a, isp_b, inet):
    r.config("router ospf 1\n network 100.64.0.0 0.0.0.7 area 0")
inet.config("router ospf 1\n network 8.8.8.0 0.0.0.255 area 0")
isp_a.config("ip route 203.0.113.0 255.255.255.0 203.0.113.2\nrouter ospf 1\n redistribute static subnets")
isp_b.config("router ospf 1\n redistribute connected subnets")

# --- EDGE: NAT --------------------------------------------------------------
attempt("EDGE/DIST", wire, edge, "g0/0/1", dist, "g0/1", "10.0.0.0/30")
edge.config("""
interface GigabitEthernet0/0/0
 ip nat outside
 ip access-group OUTSIDE-IN in
interface Serial0/1/0
 ip nat outside
 ip access-group OUTSIDE-IN in
interface GigabitEthernet0/0/1
 ip nat inside
ip access-list standard NAT-USERS
 permit 10.10.0.0 0.0.255.255
access-list 20 permit 10.20.30.0 0.0.0.255
ip nat pool SRV-POOL 203.0.113.64 203.0.113.70 netmask 255.255.255.192
ip nat inside source list NAT-USERS interface GigabitEthernet0/0/0 overload
ip nat inside source list 20 pool SRV-POOL
ip nat inside source static 10.20.30.25 203.0.113.25
ip nat inside source static tcp 10.20.30.80 80 203.0.113.80 8080
ip nat inside source static udp 10.20.30.80 53 203.0.113.80 53
route-map VIA-ISP-B permit 10
 match ip address NAT-USERS
 match interface Serial0/1/0
ip nat inside source route-map VIA-ISP-B interface Serial0/1/0 overload
ip access-list extended OUTSIDE-IN
 permit tcp any any established
 permit icmp any any echo-reply
 permit icmp any any unreachable
 permit icmp any host 203.0.113.25 echo
 permit tcp any host 203.0.113.80 eq 8080
 permit udp any host 203.0.113.80 eq domain
 permit udp any eq domain any
 permit ospf any any
 deny ip any any
""")

# --- EDGE: tracked default, floating backup, OSPF inside --------------------
edge.config("""
ip sla 1
 icmp-echo 203.0.113.1 source-interface GigabitEthernet0/0/0
 frequency 5
ip sla schedule 1 life forever start-time now
track 1 ip sla 1 reachability
ip route 0.0.0.0 0.0.0.0 203.0.113.1 track 1
ip route 0.0.0.0 0.0.0.0 198.51.100.1 200
router ospf 1
 router-id 10.0.0.1
 network 10.0.0.0 0.0.0.3 area 0
 default-information originate
""")

# --- EDGE: DHCP for two VLANs (reached by relay) ----------------------------
POOLS = {"STAFF": "10.10.10.0/24", "GUEST": "10.10.20.0/24"}
for name, cidr in POOLS.items():
    edge.config(f"""
ip dhcp excluded-address {plain(cidr, 1)} {plain(cidr, 20)}
ip dhcp pool {name}
 network {mask(cidr)}
 default-router {plain(cidr, 1)}
 dns-server 8.8.8.8
 domain-name {name.lower()}.example
""")

# --- DIST: router on a stick, relay, local pool, ACLs -----------------------
VLANS = {
    10: ("STAFF", "10.10.10.0/24"),
    20: ("GUEST", "10.10.20.0/24"),
    30: ("SERVERS", "10.20.30.0/24"),
    40: ("LAB", "10.10.40.0/24"),
    99: ("NATIVE", "10.99.99.0/24"),
}
dist.config("interface g0/0\n no shutdown")
for vid, (name, cidr) in VLANS.items():
    enc = f"dot1Q {vid}" + (" native" if vid == 99 else "")
    lines = [
        f"interface g0/0.{vid}",
        f" description {name}",
        f" encapsulation {enc}",
        f" ip address {plain(cidr, 1)} {nw(cidr).netmask}",
    ]
    if name in POOLS:
        lines.append(" ip helper-address 10.0.0.1")
    dist.config(lines)
dist.config("""
ip dhcp excluded-address 10.10.40.1 10.10.40.9
ip dhcp pool LAB
 network 10.10.40.0 255.255.255.0
 default-router 10.10.40.1
 dns-server 8.8.8.8
access-list 110 deny tcp 10.10.10.0 0.0.0.255 10.20.30.0 0.0.0.255 eq telnet
access-list 110 permit ip any any
ip access-list extended GUEST-OUT
 deny ip any 10.0.0.0 0.255.255.255
 permit ip any any
ip access-list extended SERVERS-OUT
 permit tcp any host 10.20.30.80 eq www
 permit udp any host 10.20.30.80 eq domain
 permit tcp any host 10.20.30.25 eq smtp
 permit icmp any any
 deny ip any any log
ip access-list standard MGMT
 permit 10.10.10.0 0.0.0.255
 deny any
interface GigabitEthernet0/0.10
 ip access-group 110 in
interface GigabitEthernet0/0.20
 ip access-group GUEST-OUT in
interface GigabitEthernet0/0.30
 ip access-group SERVERS-OUT out
line vty 0 4
 access-class MGMT in
 transport input telnet
router ospf 1
 router-id 10.0.0.2
 network 10.0.0.0 0.0.0.3 area 0
 network 10.10.0.0 0.0.255.255 area 0
 network 10.20.30.0 0.0.0.255 area 0
 network 10.99.99.0 0.0.0.255 area 0
""")

sw = net.switch("SW-ACCESS", at=(600, 620))
dist["g0/0"].connect(sw["g0/1"])
sw.config(
    "interface g0/1\n switchport mode trunk\n switchport trunk native vlan 99\n"
    " switchport trunk allowed vlan 10,20,30,40,99"
)
for vid, (name, _) in VLANS.items():
    sw.add_vlan(vid, name)
hosts = [
    ("PC-STAFF1", net.pc, 10, None),
    ("PC-STAFF2", net.pc, 10, None),
    ("LAPTOP-GUEST", net.laptop, 20, None),
    ("WEB", net.server, 30, "10.20.30.80"),
    ("MAIL", net.server, 30, "10.20.30.25"),
    ("PC-LAB", net.pc, 40, None),
]
for i, (name, make, vid, ip) in enumerate(hosts, 1):
    d = make(name, at=(350 + 100 * i, 760), ip=f"{ip}/24" if ip else None, gateway="10.20.30.1" if ip else "")
    if not ip:
        d.use_dhcp()
    sw[f"fa0/{i}"].connect(d["fa0"])
    sw.config(f"interface fa0/{i}\n switchport mode access\n switchport access vlan {vid}")

print("EDGE sub-config sanity:", edge.interface_config("GigabitEthernet0/0/0"))
print("DIST g0/0.99:", dist.interfaces.get("GigabitEthernet0/0.99"))
net.around(isp_a, isp_b, inet, inet_sw, dns, out_pc, shape="rectangle", outline="grey", label="INTERNET")
net.around(edge, dist, sw, *[h[0] for h in hosts], shape="rectangle", outline="blue", label="SITE: NAT, ACL, DHCP")
finish(net, "rt04_nat_acl_dhcp")
