"""Inter-VLAN routing on one router: a trunk, sub-interfaces, PCs per VLAN.

    uv run python examples/labs/router_on_a_stick.py

Add a department to VLANS and run it again; the switch ports, sub-interfaces
and addresses follow.
"""

import ipaddress

import pktlib

VLANS = {10: "Sales", 20: "Tech", 30: "Admin"}
PCS_PER_VLAN = 2

net = pktlib.new()
r1 = net.router("R1", at=(600, 120))
sw = net.switch("SW1", at=(600, 260))
r1["fa0/0"].connect(sw["fa0/1"])

sw_cfg = ["interface fa0/1", " switchport mode trunk"]
r1_cfg = ["interface fa0/0", " no shutdown"]
port = 2
for n, (vid, name) in enumerate(VLANS.items()):
    lan = ipaddress.ip_network(f"192.168.{vid}.0/24")
    gw, *hosts = lan.hosts()
    sw_cfg += [f"vlan {vid}", f" name {name}"]
    r1_cfg += [f"interface fa0/0.{vid}", f" encapsulation dot1Q {vid}", f" ip address {gw} {lan.netmask}"]
    for j in range(PCS_PER_VLAN):
        x = 200 + (n * PCS_PER_VLAN + j) * 130
        pc = net.pc(f"{name}{j + 1}", at=(x, 420), ip=f"{hosts[j]}/24", gateway=str(gw))
        sw[f"fa0/{port}"].connect(pc["fa0"])
        sw_cfg += [f"interface fa0/{port}", " switchport mode access", f" switchport access vlan {vid}"]
        port += 1

sw.config(sw_cfg)
r1.config(r1_cfg)

# ping checks, listed under the workspace
net.ping("Sales1", "Sales2", scenario="Within Sales (switched)")
net.ping("Sales1", "Tech1", scenario="Sales to Tech (routed on R1)")
net.ping("Sales1", "Admin2", scenario="Sales to Admin (routed on R1)")
net.save("router_on_a_stick.pkt")
print(f"router_on_a_stick.pkt: {len(VLANS)} VLANs, {port - 2} PCs")
