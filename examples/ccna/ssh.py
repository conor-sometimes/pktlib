"""SSH for remote management: local users, an RSA key and `transport input ssh` on a router and a switch.

    uv run python examples/ccna/ssh.py        # writes ssh.pkt

R1 and SW1 are both managed over SSH only, with the same steps on each:

  - `hostname` and `ip domain-name`: the RSA key is named after them
  - an RSA key (1024 bits). In IOS that is `crypto key generate rsa`, typed
    once and never saved in the config; Packet Tracer keeps the key in the
    device itself, so the script calls `generate_rsa_key()` instead
  - `ip ssh version 2`
  - a local user, `username admin secret ...`, and `enable secret`
  - `line vty 0 4` (0 15 on the switch) with `login local` and
    `transport input ssh`: telnet is refused, and logins use the local user

SW1 has a management address on VLAN 1 and `ip default-gateway`, so it can be
reached from ADMIN-PC's LAN through R1.

Check in Packet Tracer:
  - R1 `show ip ssh`: SSH Enabled - version 2.0
  - ADMIN-PC Desktop > Command Prompt `ssh -l admin 192.168.1.1`, password
    Adm1nPass: the R1> prompt; `enable` with En4ble
  - ADMIN-PC `ssh -l admin 192.168.10.2`: SW1's prompt, from the other LAN
  - ADMIN-PC `telnet 192.168.1.1`: refused (transport input ssh)
  - R1 `show users` while logged in: a vty line in use from 192.168.1.10
"""

import pktlib

USER, PASSWORD, ENABLE = "admin", "Adm1nPass", "En4ble"
VTY = f"""
ip domain-name ccna.lab
ip ssh version 2
username {USER} secret {PASSWORD}
enable secret {ENABLE}
"""

net = pktlib.new()
r1 = net.router("R1", "2911", at=(400, 150))
sw1 = net.switch("SW1", "2960-24TT", at=(700, 150))
admin = net.pc("ADMIN-PC", at=(150, 150), ip="192.168.1.10/24", gateway="192.168.1.1")
user = net.pc("USER-PC", at=(900, 300), ip="192.168.10.20/24", gateway="192.168.10.1")

r1["g0/0"].connect(admin["fa0"])
r1["g0/0"].address = "192.168.1.1/24"
r1["g0/1"].connect(sw1["g0/1"])
r1["g0/1"].address = "192.168.10.1/24"
sw1["fa0/1"].connect(user["fa0"])

r1.config(VTY + "line vty 0 4\n login local\n transport input ssh")
sw1.config(
    VTY
    + """
interface vlan 1
 ip address 192.168.10.2 255.255.255.0
 no shutdown
ip default-gateway 192.168.10.1
line vty 0 15
 login local
 transport input ssh
"""
)
for d in (r1, sw1):
    d.generate_rsa_key(1024)
    key = d.rsa_key
    if key is not None:
        print(f"{d.name}: RSA key {key.name}, {key.bits} bits")

net.around(admin, shape="ellipse", outline="blue", label="ssh -l admin", pad=30)
net.note("SSH only: login local,\ntransport input ssh", at=(480, 60))

net.ping("ADMIN-PC", "R1", ip="192.168.1.1", scenario="Admin to the router it will SSH to")
net.ping("ADMIN-PC", "SW1", ip="192.168.10.2", scenario="Admin to the switch management address")
net.ping("ADMIN-PC", "USER-PC", scenario="Admin to the user LAN")

net.save("ssh.pkt")
print(f"ssh.pkt: {len(net.devices)} devices, {len(net.links)} links")
