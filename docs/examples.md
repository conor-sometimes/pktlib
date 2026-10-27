# Examples

Each one opened in Packet Tracer 8.2 and tested there. Run one with
`just example NAME`, or `just examples` for all of them (built into `out/` and audited).


| example | what it is | checked in Packet Tracer |
|---|---|---|
| `ospf_ring.py [N] [pcs]` | N routers in a serial OSPF ring, auto-addressed | pings across the ring (TTL shows 3 hops) |
| `router_on_a_stick.py` | 3 VLANs, trunk, sub-interfaces | Sales to Admin ping through the router |
| `datacenter.py` | edge router, 2 cores with HSRP + OSPF + an LACP EtherChannel, 4 leaves, 12 servers, office with PoE switch, 6 IP phones, DHCP, CME | server to 8.8.8.8 4/4; office PC gets DHCP through its phone and reaches the DB VLAN; all 6 phones registered with CME (1001-1006); Po1(SU) between the cores |
| `enterprise.py` | two ISPs on eBGP; dual-homed HQ (ISR4331 + 2911) with NAT overload, a static NAT web server, 3650 cores with LACP + HSRP + OSPF + DHCP, a guest VLAN behind an ACL; branch 1 on OSPF area 1 (an 1841 with a WIC-2T added), branch 2 on EIGRP redistributed into OSPF (a 2911 with an HWIC-2T added), CME and IP phones | both branches reach 8.8.8.8 and 1.1.1.1 through NAT; the internet reaches 192.0.2.80; staff PC gets DHCP and reaches 1.1.1.1; guest gets DHCP, reaches 8.8.8.8 and is refused HQ-WEB; branch 1 PC gets DHCP from its router; 3 phones registered |
| `datacentres.py` | five sites (DUBLIN, LONDON, PARIS, FRANKFURT, AMSTERDAM) in a full serial mesh, OSPF area 0 between them and an area per site; each site has a 2911 border with two HWIC-2Ts, 3650 cores with LACP + HSRP, two leaves and four servers | DUBLIN-BR FULL with all four other borders; pings to PARIS-WEB1 and AMSTERDAM-DB2 |
| `solar_system.py` | for fun: a 3650 sun with a routed link to 8 planet 2911s, the planets in a serial ring, OSPF over all of it, residents on every planet, ET-PHONE-HOME IP phones on Earth with CME, and Pluto with no cable | opens and draws in Packet Tracer; the audit flags Pluto and only Pluto (pings not tried) |
| `practice_lab.py [seed]` | random routing lab, routers left blank, answer key | built and audited |
| `fault_lab.py [handed_in.pkt]` | router on a stick with two faults to find (`pktlib.lab`), answer key, grading | built and audited; not opened yet |
| `stress/` (`just stress`) | 14 deliberately hard networks written by two agents told to break pktlib: five EtherChannel kinds on one switch, 24 VLANs, HSRP on 21 SVIs, 24 phones, three-way redistribution, OSPF stub/NSSA/virtual links, five-AS BGP, every NAT kind, dual stack with GRE, a 14-hop RIP chain, home and ISP kit | the ones that found bugs, after the fix: 5 channels up and OSPF over the L3 ones; phones registered; OSPFv3 and IPv6 EIGRP routes learned |
