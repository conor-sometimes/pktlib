# Examples

Every script builds a network and saves it as a `.pkt` next to where you run it. Each is
built and audited by the tests, and has ping checks you can click in Packet Tracer.
Which ones have been opened in Packet Tracer itself is in
[docs/examples.md](../docs/examples.md).

```
uv run python examples/labs/ospf_ring.py
```

This page is generated: `uv run python scripts/examples.py index`.

## labs

Classroom labs: small networks to hand out, with answer keys and grading.

- [`fault_lab.py`](labs/fault_lab.py): A troubleshooting lab: router on a stick with two faults to find.
- [`ospf_ring.py`](labs/ospf_ring.py): N routers in a serial ring running OSPF, each with its own LAN.
- [`practice_lab.py`](labs/practice_lab.py): A random routing lab to practise on, plus its answer key.
- [`router_on_a_stick.py`](labs/router_on_a_stick.py): Inter-VLAN routing on one router: a trunk, sub-interfaces, PCs per VLAN.

## ccna

One network per CCNA topic, each with ping checks that prove it works.

- [`acl.py`](ccna/acl.py): Access control lists: a standard ACL, a numbered extended ACL and a named extended ACL on one router.
- [`dhcp.py`](ccna/dhcp.py): DHCP from a router: a local pool for its own LAN, and a relayed pool for a branch LAN with `ip helper-address`.
- [`dhcp_snooping.py`](ccna/dhcp_snooping.py): DHCP snooping: a rogue DHCP server on an access port is ignored, so clients get the real gateway.
- [`eigrp.py`](ccna/eigrp.py): EIGRP on three routers, with a fast path, a slow serial backup and a feasible successor.
- [`etherchannel.py`](ccna/etherchannel.py): EtherChannel two ways: an LACP bundle and a PAgP bundle, both trunking to a multilayer switch.
- [`hsrp.py`](ccna/hsrp.py): HSRP: two routers share one virtual gateway address, so the LAN survives losing either.
- [`intervlan_mls.py`](ccna/intervlan_mls.py): Inter-VLAN routing on a multilayer switch: SVIs, `ip routing` and a routed uplink port.
- [`ipv6.py`](ccna/ipv6.py): IPv6 next to IPv4: global and link-local addresses, OSPFv3 between two routers, static routes to a stub branch.
- [`nat.py`](ccna/nat.py): NAT three ways on one edge router: static NAT for a server, a dynamic pool, and PAT (overload).
- [`ospf_dr_election.py`](ccna/ospf_dr_election.py): OSPF DR and BDR election on a shared Ethernet segment, decided by interface priority.
- [`ospf_multi_area.py`](ccna/ospf_multi_area.py): Multi-area OSPF: a backbone with two area border routers, each leading to its own area.
- [`ospf_single_area.py`](ccna/ospf_single_area.py): Single-area OSPF on a triangle of routers, with router IDs, passive LANs and a default route.
- [`port_security.py`](ccna/port_security.py): Port security on an access switch: sticky MACs, a static MAC, and a rogue PC that gets its port shut.
- [`ripv2.py`](ccna/ripv2.py): Three routers in a line running RIPv2, with discontiguous subnets that need no auto-summary.
- [`ssh.py`](ccna/ssh.py): SSH for remote management: local users, an RSA key and `transport input ssh` on a router and a switch.
- [`static_routes.py`](ccna/static_routes.py): Static routes, a default route and a floating static backup between two sites.
- [`stp.py`](ccna/stp.py): Spanning tree on a switch triangle: a chosen root bridge per VLAN, PortFast and BPDU guard.
- [`vlans_trunks.py`](ccna/vlans_trunks.py): VLANs on two switches joined by an 802.1Q trunk, with a native VLAN and a pruned allowed list.
- [`voice_cme.py`](ccna/voice_cme.py): IP phones on a voice VLAN: a PoE switch, PCs behind the phones, and a router running CME.

## showcase

Big, realistic networks that show what pktlib can build.

- [`campus.py`](showcase/campus.py): A university campus: five buildings, a VLAN per department, HSRP cores, guest network behind ACLs.
- [`datacenter.py`](showcase/datacenter.py): A small data centre and an office, behind one edge router.
- [`datacentres.py`](showcase/datacentres.py): Five data centres, every one linked to every other.
- [`enterprise.py`](showcase/enterprise.py): A dual-homed enterprise: two ISPs, an HQ campus, two branches over serial WAN.
- [`home_lab.py`](showcase/home_lab.py): A home lab: the family network on a Linksys, and a study rack behind its own router.
- [`hospital.py`](showcase/hospital.py): A hospital and its outpatient clinic, with clinical, medical device, admin and guest networks kept apart.
- [`hub_and_spoke.py`](showcase/hub_and_spoke.py): A hub-and-spoke WAN: six branch offices on serial links to one head office hub, EIGRP over all of it.
- [`isp_backbone.py`](showcase/isp_backbone.py): An ISP backbone: four POPs in an OSPF ring, a BGP border to the internet, and customer sites.
- [`redistribution.py`](showcase/redistribution.py): Four routing domains, OSPF, EIGRP, RIP and static, joined by one router that redistributes between them all.
- [`small_business.py`](showcase/small_business.py): A small business with IP phones: one router does routing, DHCP, NAT and call control (CME).
- [`solar_system.py`](showcase/solar_system.py): The solar system, as a network. For fun.
- [`starship.py`](showcase/starship.py): A starship, as a network: decks on VLANs, twin cores, shuttles that dock on serial, and a starbase far away. For fun.

## recipes

Short scripts for one job each: read a file, check a folder of hand-ins, ...

- [`addressing_csv.py`](recipes/addressing_csv.py): Export a network's addressing table (device, interface, address, mask, gateway, VLAN) to CSV.
- [`audit_folder.py`](recipes/audit_folder.py): Audit a folder of handed-in .pkt files and print one table row per student.
- [`bulk_pcs.py`](recipes/bulk_pcs.py): Add 30 PCs from a table (name, address, VLAN), each on the next free switch port, in a tidy grid.
- [`check_passwords.py`](recipes/check_passwords.py): Check every device's passwords against the ones a lab brief asked for, hashed or not.
- [`diff_pkt.py`](recipes/diff_pkt.py): Diff two .pkt files: devices, cables, addresses and config.
- [`find_vlan.py`](recipes/find_vlan.py): Find everything in one VLAN: access and voice ports, the devices on them, trunks that carry it, its gateways.
- [`grade_folder.py`](recipes/grade_folder.py): Grade a folder of submissions against a `pktlib.Lab` and print a mark sheet.
- [`inventory.py`](recipes/inventory.py): List every device, port, address and cable in a .pkt file.
- [`random_labs.py`](recipes/random_labs.py): Generate N random subnetting labs, each with a student file, a solution and an answer key.
- [`rename_devices.py`](recipes/rename_devices.py): Rename every device to a naming scheme (SITE-ROLE-NN), hostnames included.
- [`swap_model.py`](recipes/swap_model.py): Replace every router of one model with another (1841 to 1941 here), keeping cables, config and ping checks.
- [`tidy_grid.py`](recipes/tidy_grid.py): Move a messy network's devices into a tidy layout: routers on top, switches below, each host under its switch.
- [`to_script.py`](recipes/to_script.py): Turn any .pkt into a Python script that rebuilds it, then check the rebuild matches.
