"""Port security on an access switch: sticky MACs, a static MAC, and a rogue PC that gets its port shut.

    uv run python examples/ccna/port_security.py        # writes port_security.pkt

SW1's host ports each allow only known MAC addresses:

  Fa0/1  PC1: `maximum 2`, `mac-address sticky` (the switch learns the first
         two MACs it sees and writes them into the running config),
         `violation restrict` (frames from a third MAC are dropped and counted)
  Fa0/2  PC2: its own MAC configured by hand (`mac-address 00xx.xxxx.xxxx`)
  Fa0/3  meant for a registered laptop whose MAC is configured, but a ROGUE PC
         is plugged in instead. The default violation mode is `shutdown`, so
         the first frame from the wrong MAC puts the port in err-disabled
         state and ROGUE is cut off

The script reads PC2's MAC from the file it builds, so the static entry
always matches. SERVER and R1 sit on ports without port security.

Check in Packet Tracer:
  - SW1 `show port-security`: Fa0/1 max 2 Restrict, Fa0/2 and Fa0/3 max 1
    Shutdown; after ROGUE's ping, Fa0/3 shows a security violation count of 1
  - SW1 `show port-security interface fa0/3`: Port Status Secure-shutdown
  - SW1 `show interfaces fa0/3 status` (or `show interfaces status`): err-disabled
  - SW1 `show port-security address`: PC1's MAC as SecureSticky, PC2's as
    SecureConfigured
  - To recover Fa0/3: `shutdown` then `no shutdown` on it (it fails again
    while ROGUE is still there)
"""

import pktlib

REGISTERED_LAPTOP = "0060.2f11.2233"  # the MAC Fa0/3 expects; ROGUE doesn't have it

net = pktlib.new()
r1 = net.router("R1", "2911", at=(500, 60))
sw = net.switch("SW1", "2960-24TT", at=(500, 220))
server = net.server("SERVER", at=(800, 220), ip="192.168.1.100/24", gateway="192.168.1.1")
r1["g0/0"].connect(sw["g0/1"])
r1["g0/0"].address = "192.168.1.1/24"
sw["fa0/24"].connect(server["fa0"])

pcs = {}
for i, name in enumerate(("PC1", "PC2", "ROGUE"), 1):
    pcs[name] = net.pc(name, at=(300 + 200 * (i - 1), 400), ip=f"192.168.1.{10 + i}/24", gateway="192.168.1.1")
    sw[f"fa0/{i}"].connect(pcs[name]["fa0"])

pc2_mac = pcs["PC2"]["fa0"].mac.lower()
sw.config(f"""
interface fa0/1
 switchport mode access
 switchport port-security
 switchport port-security maximum 2
 switchport port-security mac-address sticky
 switchport port-security violation restrict
interface fa0/2
 switchport mode access
 switchport port-security
 switchport port-security mac-address {pc2_mac}
interface fa0/3
 switchport mode access
 switchport port-security
 switchport port-security mac-address {REGISTERED_LAPTOP}
""")

net.note("Fa0/1 sticky, max 2", at=(240, 470))
net.note(f"Fa0/2 static\n{pc2_mac}", at=(450, 470))
net.note(f"Fa0/3 expects {REGISTERED_LAPTOP}\nviolation: shutdown", at=(660, 470))
net.around("ROGUE", shape="ellipse", outline="red", label="not the registered laptop", pad=30)

net.ping("PC1", "SERVER", scenario="Sticky MAC port to the server")
net.ping("PC2", "SERVER", scenario="Static MAC port to the server")
net.ping("ROGUE", "SERVER", scenario="Rogue PC to the server: should FAIL")

net.save("port_security.pkt")
print(f"port_security.pkt: {len(net.devices)} devices, {len(net.links)} links")
