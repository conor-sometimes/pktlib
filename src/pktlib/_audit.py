"""Lint a network before you hand it in: what can be checked without running
the simulation.

    pktlib audit lab.pkt            # from a shell; exits 1 if it finds anything
    problems = pktlib.audit(net)    # from Python

Duplicate addresses (MAC, IPv4, IPv6 link-local), config Packet Tracer 8.2 is
known to refuse, PC gateways nobody owns, the two ends of a link in different
subnets, cabled ports left shut down, serial DCE ends with no clock rate,
routers with more than one network and no routing at all, shared OSPF
router-ids, router ports given their subnet's network or broadcast address, or
a subnet that overlaps another port's on the same router.
A clean audit doesn't prove a ping works: still test in Packet Tracer.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict

from ._iosconfig import blocks, refused
from ._model import Device, Network

GIGABIT_ONLY = {"PT-REPEATER-NM-1CGE": "PT-REPEATER-NM-1CFE"}  # card -> the FastEthernet one to use


class Problem(str):
    """One thing the audit found: the sentence it prints, plus `devices`,
    the names of the devices involved (for a grader to point at)."""

    devices: tuple[str, ...]

    def __new__(cls, text: str, *devices: str) -> Problem:
        p = super().__new__(cls, text)
        p.devices = tuple(dict.fromkeys(devices))
        return p


def _iface(addr: str | None) -> ipaddress.IPv4Interface | None:
    """The address as an interface, or None when there's none or it's damaged."""
    try:
        return ipaddress.IPv4Interface(addr) if addr else None
    except ValueError:
        return None


def audit(net: Network) -> list[Problem]:
    """Everything wrong that can be seen in the file, one Problem each."""
    problems: list[Problem] = []
    owners: dict[str, list[tuple[str, str]]] = defaultdict(list)  # ip -> [(device, port), ...]
    router_ifaces: list[tuple[Device, str, ipaddress.IPv4Interface]] = []
    gateways: set[str] = set()  # addresses a host may use as its gateway, HSRP virtual IPs included
    for d in net.devices:
        lan = d.engine.findtext("LAN_IP_ADDRESS")
        if lan:  # a home router's LAN address, set in its GUI (192.168.0.1 out of the box)
            gateways.add(lan)
        if d.has_ios:  # every interface in the config, sub-interfaces and SVIs included
            earlier: list[tuple[str, ipaddress.IPv4Network]] = []
            for name, (addr, _up) in d.interfaces.items():
                if addr:
                    try:
                        iface = ipaddress.IPv4Interface(addr)
                    except ValueError:
                        problems.append(Problem(f"{d.name}.{name}: {addr} isn't an IPv4 address and mask", d.name))
                        continue
                    owners[str(iface.ip)].append((d.name, name))
                    router_ifaces.append((d, name, iface))
                    # Packet Tracer 8.2 drops either silently when it loads the file and the
                    # port ends up with no address (checks 6 and 25, 27 Oct 2026)
                    nw = iface.network
                    if nw.prefixlen < 31 and iface.ip in (nw.network_address, nw.broadcast_address):
                        which = "network" if iface.ip == nw.network_address else "broadcast"
                        problems.append(
                            Problem(
                                f"{d.name}.{name}: {iface.ip} is the {which} address of {nw}; "
                                "Packet Tracer drops it, so the port has no address",
                                d.name,
                            )
                        )
                    # Packet Tracer replays the config in order and drops an address
                    # whose subnet overlaps an earlier port's (check 6, 27 Oct 2026:
                    # 10.0.0.130/25 on g0/2 after 10.0.0.129/25 on g0/1)
                    clash = next((n for n, other in earlier if other.overlaps(nw)), None)
                    if clash is not None:
                        problems.append(
                            Problem(
                                f"{d.name}.{name}: {iface} overlaps {clash}'s subnet; "
                                "Packet Tracer drops it, so the port has no address",
                                d.name,
                            )
                        )
                    earlier.append((name, nw))
                    gateways.add(str(iface.ip))
                for key, line in d.interface_config(name).items():
                    if key.startswith("standby ") and key.endswith(" ip"):
                        gateways.add(line.split()[-1])
                    elif line.startswith("ip address ") and line.endswith(" secondary"):
                        gateways.add(line.split()[2])  # a second subnet on the same port
        else:
            for p in d:
                if p.address:
                    host = _iface(p.address)
                    if host is None:
                        problems.append(
                            Problem(f"{d.name}.{p.name}: {p.address} isn't an IPv4 address and mask", d.name)
                        )
                        continue
                    owners[str(host.ip)].append((d.name, p.name))

    for mac, who in net.duplicate_macs().items():
        problems.append(
            Problem(
                f"MAC {mac} is used by more than one device: {', '.join(who)}",
                *(w.split()[0].split(".")[0] for w in who),
            )
        )
    for ll, who in net.duplicate_link_locals().items():
        problems.append(
            Problem(
                f"IPv6 link-local {ll} is on more than one device: {', '.join(who)}", *(w.split(".")[0] for w in who)
            )
        )
    # two routers with one OSPF router-id: PT left the link in EXSTART and no
    # OSPF route anywhere (the solar system example, 26 Oct 2026)
    rids: dict[str, list[str]] = defaultdict(list)
    for d in net.devices:
        for header, body in blocks(d.running_config) if d.has_ios else []:
            if header.startswith("router ospf "):
                for line in body:
                    if line.startswith("router-id "):
                        rids[line.split()[1]].append(d.name)
    for rid, names in rids.items():
        if len(names) > 1:
            problems.append(Problem(f"OSPF router-id {rid} is on more than one router: {', '.join(names)}", *names))
    for d in net.devices:
        for line, why in refused(d.running_config, d.model) if d.has_ios else []:
            problems.append(Problem(f"{d.name}: `{line.strip()}` {why}", d.name))

    for ip, where in owners.items():
        if len(where) > 1:
            problems.append(
                Problem(
                    f"{ip} is on more than one port: {', '.join(f'{a}.{b}' for a, b in where)}", *(a for a, _ in where)
                )
            )

    for d in net.devices:
        if d.has_ios or d.dhcp or d.kind == "IpPhone":  # DHCP clients get theirs when the file opens
            continue
        for p in d:
            if p.el.find("IP") is None or p.type in ("eCopperCoaxial", "eModem"):  # no IP over coax or phone line
                continue
            if not p.address:
                if p.link:
                    problems.append(Problem(f"{d.name}.{p.name} is cabled but has no IP", d.name))
                continue
            host = _iface(p.address)
            if host is None:  # reported above
                continue
            if not d.gateway:
                # only a problem when there's a router address in its subnet to point at:
                # a switch-only lab has no gateway to give (found by the CCNA examples)
                if any(i.network == host.network for _, _, i in router_ifaces):
                    problems.append(Problem(f"{d.name} has no default gateway", d.name))
            elif d.gateway not in gateways:
                problems.append(Problem(f"{d.name}'s gateway {d.gateway} isn't any router's address", d.name))
            elif ipaddress.IPv4Address(d.gateway) not in host.network:
                problems.append(Problem(f"{d.name}'s gateway {d.gateway} is outside {host.network}", d.name))

    for link in net.links:
        pa, pb = link.ports
        (a, ap), (b, bp) = link.ends
        for p in (pa, pb):
            if p.device.has_ios and p.device.kind == "Router" and not p.up:
                problems.append(Problem(f"{p.device.name}.{p.name} is cabled but shut down", p.device.name))
        ia, ib = _iface(pa.address), _iface(pb.address)
        if ia is not None and ib is not None:
            na, nb = ia.network, ib.network
            if na != nb:
                problems.append(
                    Problem(f"{a}.{ap} ({na}) and {b}.{bp} ({nb}) are cabled together but in different subnets", a, b)
                )
        for p, other in ((pa, pb), (pb, pa)):
            # the AccessPoint-PT-AC's stock card won't step down to 100 Mb/s
            # (seen in Packet Tracer 8.2: red to Fa0/1 and to a PC, green to Gi0/1)
            if p.module in GIGABIT_ONLY and other.type != "eCopperGigabitEthernet":
                problems.append(
                    Problem(
                        f"{p.device.name}.{p.name} ({p.module}) only links to gigabit ports, not "
                        f"{other.device.name}.{other.name}; fit {GIGABIT_ONLY[p.module]} instead",
                        p.device.name,
                        other.device.name,
                    )
                )
        if link.cable == "serial" and link.dce:
            dce = net.device(link.dce.device)[link.dce.port]
            if not dce.setting("clock rate"):
                problems.append(
                    Problem(f"{dce.device.name}.{dce.name} is the DCE end with no clock rate", dce.device.name)
                )

    routers = [d for d in net.devices if d.kind == "Router"]
    for d in routers if len(routers) > 1 else []:  # one router routes between its own networks
        nets = {str(i.network) for dev, _, i in router_ifaces if dev.name == d.name}
        routing = any(line.startswith(("router ", "ip route ")) for line in d.running_config)
        if len(nets) > 1 and not routing:
            problems.append(
                Problem(f"{d.name} has {len(nets)} networks but no routing protocol or static route", d.name)
            )
    return problems
