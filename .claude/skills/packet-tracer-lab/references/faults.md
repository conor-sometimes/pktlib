# Fault labs

Break a network that already passed the audit, one fault at a time, in the script, so the
answer key can say exactly what changed.

Some faults the audit reports. Students with pktlib can find those in one command, so say in
the key which kind each fault is.

The audit reports these:
- a PC gateway no router owns;
- a cabled port left shut down;
- a serial DCE end with no clock rate;
- the two ends of a link in different subnets;
- a duplicate IP or MAC;
- a router with several networks and no routing at all.

The audit doesn't see these, so they need `show` commands:
- a missing or wrong `network` statement, or the wrong OSPF area or wildcard;
- an access port in the wrong VLAN, or a VLAN missing from the switch;
- a trunk that doesn't allow a VLAN, or a native VLAN mismatch;
- an ACL in the wrong place or direction;
- a wrong static route next hop.

`Lab.build` checks this for you (it runs the audit unless `audit=False`): a visible fault needs `audit_says`
(a piece of the audit's line), and any other line the audit gives stops the build.

Watch the `fixed` check: `interface_config()` leaves `shutdown` out, so check a port's state
with `device.interfaces[name][1]`. If a check is wrong, the build says the fault "should
fail but passes".
