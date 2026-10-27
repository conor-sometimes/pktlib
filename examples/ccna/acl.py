"""Access control lists: a standard ACL, a numbered extended ACL and a named extended ACL on one router.

    uv run python examples/ccna/acl.py        # writes acl.pkt

R1 routes between three LANs: STAFF (Gi0/0), GUEST (Gi0/1) and SERVERS
(Gi0/2, a file server and a web server). Four lists control who reaches what:

  access-list 10      standard, out on Gi0/2 (close to the destination, as
                      standard ACLs match the source only): STAFF2, a
                      contractor, is kept off the server LAN
  access-list 110     extended, in on Gi0/0 (close to the source): staff
                      can't ping into the guest LAN; everything else allowed
  GUEST-IN            named extended, in on Gi0/1: guests get the web server
                      on port 80 and can ping their own gateway, nothing else
                      (the implicit `deny any` at the end, written out here)
  VTY-ADMINS          named standard, `access-class` on the vty lines: only
                      STAFF1 may telnet to the router

Three of the ping scenarios are expected to fail: that is the ACLs working.

Check in Packet Tracer:
  - R1 `show access-lists`: all four lists, with match counts after the pings
  - R1 `show ip interface g0/1`: Inbound access list is GUEST-IN
  - GUEST1 Desktop > Web Browser `http://192.168.30.20` loads; GUEST1
    `ping 192.168.30.20` fails (only port 80 is allowed)
  - STAFF2 `ping 192.168.30.10` fails (access-list 10); STAFF1's works
  - STAFF1 `telnet 192.168.10.1` asks for the password (cisco);
    STAFF2 `telnet 192.168.10.1` is refused (VTY-ADMINS)
"""

import pktlib

net = pktlib.new()
r1 = net.router("R1", "2911", at=(500, 260))

LANS = {"STAFF": ("g0/0", 10, (200, 400)), "GUEST": ("g0/1", 20, (800, 400)), "SERVERS": ("g0/2", 30, (500, 140))}
switch = {}
for name, (port, n, xy) in LANS.items():
    sw = net.switch(f"SW-{name}", at=xy)
    r1[port].connect(sw["g0/1"])
    r1[port].address = f"192.168.{n}.1/24"
    switch[name] = sw

hosts = [  # (name, kind, lan, last octet, x, y)
    ("STAFF1", net.pc, "STAFF", 11, 120, 540),
    ("STAFF2", net.pc, "STAFF", 12, 280, 540),
    ("GUEST1", net.laptop, "GUEST", 21, 720, 540),
    ("GUEST2", net.laptop, "GUEST", 22, 880, 540),
    ("FILES", net.server, "SERVERS", 10, 350, 20),
    ("WEB", net.server, "SERVERS", 20, 650, 20),
]
for i, (name, make, lan, last, x, y) in enumerate(hosts):
    n = LANS[lan][1]
    h = make(name, at=(x, y), ip=f"192.168.{n}.{last}/24", gateway=f"192.168.{n}.1")
    sw = switch[lan]
    sw[f"fa0/{1 + sum(1 for hh in hosts[:i] if hh[2] == lan)}"].connect(h["fa0"])

r1.config("""
access-list 10 deny host 192.168.10.12
access-list 10 permit any
access-list 110 deny icmp 192.168.10.0 0.0.0.255 192.168.20.0 0.0.0.255
access-list 110 permit ip any any
ip access-list extended GUEST-IN
 permit tcp 192.168.20.0 0.0.0.255 host 192.168.30.20 eq www
 permit icmp 192.168.20.0 0.0.0.255 host 192.168.20.1
 deny ip any any
ip access-list standard VTY-ADMINS
 permit host 192.168.10.11
interface g0/0
 ip access-group 110 in
interface g0/1
 ip access-group GUEST-IN in
interface g0/2
 ip access-group 10 out
line vty 0 4
 password cisco
 login
 access-class VTY-ADMINS in
 transport input telnet
""")

net.around(
    "SW-STAFF", "STAFF1", "STAFF2", shape="rectangle", outline="blue", label="STAFF 192.168.10.0/24: ACL 110 in", pad=30
)
net.around(
    "SW-GUEST",
    "GUEST1",
    "GUEST2",
    shape="rectangle",
    outline="orange",
    label="GUEST 192.168.20.0/24: GUEST-IN in",
    pad=30,
)
net.around(
    "SW-SERVERS",
    "FILES",
    "WEB",
    shape="rectangle",
    outline="green",
    label="SERVERS 192.168.30.0/24: ACL 10 out",
    pad=30,
)

net.ping("STAFF1", "FILES", scenario="Staff to the file server")
net.ping("GUEST1", "R1", ip="192.168.20.1", scenario="Guest to its gateway")
net.ping("STAFF2", "FILES", scenario="Contractor to the file server: should FAIL")
net.ping("STAFF1", "GUEST1", scenario="Staff ping into the guest LAN: should FAIL")
net.ping("GUEST2", "FILES", scenario="Guest to the file server: should FAIL")

net.save("acl.pkt")
print(f"acl.pkt: {len(net.devices)} devices, {len(net.links)} links")
