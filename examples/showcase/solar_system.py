"""The solar system, as a network. For fun.

  uv run python examples/showcase/solar_system.py          # writes solar_system.pkt

the sun    a 3650 with a routed link to every planet (hub)
planets    eight 2911s in a serial ring (each with an HWIC-2T fitted), so
           every planet has three ways home; OSPF area 0 over all of it
residents  each planet has a switch and its locals on 10.<planet>.0.0/24
earth      PoE switch, voice VLAN, CME on its own router, and two IP phones
           called ET-PHONE-HOME
pluto      a PC with no cable. See the note.
"""

import math

import pktlib

PLANETS = [
    ("MERCURY", ["HOT-ROCK", "SPEEDY"]),
    ("VENUS", ["CLOUD-1", "CLOUD-2"]),
    ("EARTH", None),  # phones instead, below
    ("MARS", ["ROVER", "MARTIAN"]),
    ("JUPITER", ["IO", "EUROPA"]),
    ("SATURN", ["RING-LEADER", "TITAN"]),
    ("URANUS", ["SIDEWAYS", "COLD"]),
    ("NEPTUNE", ["TRITON", "BLUE"]),
]
COLOURS = ["grey", "orange", "blue", "red", "orange", "yellow", "teal", "blue"]
CX, CY, R = 900, 600, 430

net = pktlib.new()
sun = net.multilayer("SUN", "3650-24PS", at=(CX, CY))
# not 1.1.1.1: MERCURY, planet 1, is i.i.i.i, and a shared router-id left the
# SUN's link stuck in EXSTART and no OSPF routes anywhere (found by the pings below)
sun.config("ip routing\nrouter ospf 1\n router-id 100.100.100.100\n network 172.16.0.0 0.0.255.255 area 0")

routers = []
for i, (name, _) in enumerate(PLANETS, 1):
    angle = 2 * math.pi * (i - 1) / len(PLANETS) - math.pi / 2
    x, y = CX + R * math.cos(angle), CY + R * math.sin(angle)
    r = net.router(name, "2911", at=(x, y))
    r.add_module("HWIC-2T", slot=(0, 0))
    r["g0/0"].connect(sun[f"g1/0/{i}"])
    r["g0/0"].address = f"172.16.{i}.2/30"
    sun.config(f"interface g1/0/{i}\n no switchport\n ip address 172.16.{i}.1 255.255.255.252")
    r.config(
        f"router ospf 1\n router-id {i}.{i}.{i}.{i}\n network 172.16.{i}.0 0.0.0.3 area 0\n"
        f" network 10.{i}.0.0 0.0.255.255 area 0\n network 192.168.0.0 0.0.255.255 area 0"
    )
    routers.append((r, x, y, angle))

# the ring: each planet's Se0/0/0 (DCE) to the next planet's Se0/0/1
for i, (r, *_rest) in enumerate(routers):
    nxt = routers[(i + 1) % len(routers)][0]
    r["se0/0/0"].connect(nxt["se0/0/1"])
    r["se0/0/0"].address = f"192.168.{i + 1}.1/30"
    nxt["se0/0/1"].address = f"192.168.{i + 1}.2/30"

# residents
for i, ((name, locals_), (r, x, y, angle)) in enumerate(zip(PLANETS, routers, strict=True), 1):
    ox, oy = math.cos(angle), math.sin(angle)  # outwards from the sun
    if locals_ is None:
        continue
    sw = net.switch(f"{name}-SW", at=(x + 110 * ox, y + 110 * oy))
    r["g0/1"].connect(sw["g0/1"])
    r["g0/1"].address = f"10.{i}.0.1/24"
    for k, who in enumerate(locals_):
        side = -1 if k == 0 else 1
        pc = net.pc(
            who,
            at=(x + 200 * ox - 60 * side * oy, y + 200 * oy + 60 * side * ox),
            ip=f"10.{i}.0.{10 + k}/24",
            gateway=f"10.{i}.0.1",
        )
        sw[f"fa0/{k + 1}"].connect(pc["fa0"])

# earth: phones home
e = 3
earth = routers[e - 1][0]
ex, ey, ea = routers[e - 1][1:]
ox, oy = math.cos(ea), math.sin(ea)
esw = net.multilayer("EARTH-SW", "3560-24PS", at=(ex + 120 * ox, ey + 120 * oy))  # PoE
earth["g0/1"].connect(esw["g0/1"])
esw.config("cdp run\ninterface g0/1\n switchport trunk encapsulation dot1q\n switchport mode trunk")
esw.add_vlan(10, "HUMANS")
esw.add_vlan(20, "PHONES")
earth.config(f"""
interface g0/1
 no shutdown
interface g0/1.10
 encapsulation dot1Q 10
 ip address 10.{e}.0.1 255.255.255.0
interface g0/1.20
 encapsulation dot1Q 20
 ip address 10.{e}.20.1 255.255.255.0
ip dhcp excluded-address 10.{e}.0.1 10.{e}.0.9
ip dhcp excluded-address 10.{e}.20.1 10.{e}.20.9
ip dhcp pool HUMANS
 network 10.{e}.0.0 255.255.255.0
 default-router 10.{e}.0.1
ip dhcp pool PHONES
 network 10.{e}.20.0 255.255.255.0
 default-router 10.{e}.20.1
 option 150 ip 10.{e}.20.5
""")
cme = net.router("MISSION-CONTROL", "2811", at=(ex + 120 * ox + 170, ey + 120 * oy))
cme["fa0/0"].connect(esw["fa0/24"])
esw.config("interface fa0/24\n switchport mode access\n switchport access vlan 20")
cme["fa0/0"].address = f"10.{e}.20.5/24"
cme.config(f"""
ip route 0.0.0.0 0.0.0.0 10.{e}.20.1
telephony-service
 max-ephones 2
 max-dn 2
 ip source-address 10.{e}.20.5 port 2000
 auto assign 1 to 2
ephone-dn 1
 number 1977
ephone-dn 2
 number 1982
""")
for k in range(2):
    side = -1 if k == 0 else 1
    px, py = ex + 230 * ox - 90 * side * oy, ey + 230 * oy + 90 * side * ox
    phone = net.phone(f"ET-PHONE-HOME{k + 1}", at=(px, py))
    human = net.pc(f"HUMAN{k + 1}", at=(px + 70 * ox, py + 70 * oy))
    human.use_dhcp()
    esw[f"fa0/{k + 1}"].connect(phone["Switch"])
    phone["PC"].connect(human["fa0"])
    esw.config(f"interface fa0/{k + 1}\n switchport mode access\n switchport access vlan 10\n switchport voice vlan 20")

# pluto
pluto = net.pc("PLUTO", at=(CX + R + 380, CY + R + 60), ip="10.9.0.10/24", gateway="10.9.0.1")
net.note(
    "PLUTO: demoted in 2006.\nNo link, no gateway anyone owns.\nStill a planet in our hearts.",
    at=(CX + R + 300, CY + R + 130),
)

# drawings
net.around(sun, shape="ellipse", outline="orange", fill="yellow", label="THE SUN (OSPF area 0, hub)", pad=70)
for (name, _), (r, *_rest), colour in zip(PLANETS, routers, COLOURS, strict=True):
    members = [r] + [d for d in net.devices if d.name.startswith(f"{name}-")]
    net.around(*members, shape="ellipse", outline=colour, label=name, pad=40)
net.note(
    "Every planet: one link to the sun, two serials round the ring.\n"
    "Pull any cable and OSPF finds another way. Space is big.",
    at=(80, 60),
)
net.note("ET-PHONE-HOME1 is x1977, ET-PHONE-HOME2 is x1982.", at=(80, 120))

# ping checks, under the workspace: double-click Fire once OSPF has settled
for _name, locals_ in PLANETS[1:]:
    if locals_:
        net.ping("HOT-ROCK", locals_[0], scenario="Grand tour")  # Mercury to everyone
net.ping("ROVER", "MISSION-CONTROL", scenario="Grand tour")  # Mars calls Houston
net.ping("TRITON", "HUMAN1", ip="10.3.0.1", scenario="Grand tour")  # humans use DHCP, so their gateway
net.ping("HUMAN1", "SIDEWAYS", scenario="Earth calls Uranus")
net.ping("HUMAN2", "COLD", scenario="Earth calls Uranus")
net.ping("PLUTO", "HOT-ROCK", scenario="Pluto (fails, as it should)")
net.ping("PLUTO", "MISSION-CONTROL", scenario="Pluto (fails, as it should)")  # can't phone Earth either

net.save("solar_system.pkt")
print(
    f"solar_system.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.shapes)} shapes, "
    f"{len(net.notes)} notes"
)
