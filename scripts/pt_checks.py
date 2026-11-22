"""Build the files to check in Packet Tracer, and the checklist that goes with them.

    uv run python scripts/pt_checks.py            # writes out/pt-checks/*.pkt and CHECKS.md
    uv run python scripts/pt_checks.py 3          # round 3 (TODO.md): out/pt-checks-3/

For whoever has Packet Tracer 8.2.0 (build 8.2.0.0162). Open each file, do what its
entry says, and write down what Packet Tracer did. Each answer either confirms something
pktlib already does or tells us what to change; both end up as a test with the date in it.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pktlib  # noqa: E402
from pktlib._xml import req  # noqa: E402
from pktlib.activity import Activity, diff_items, make_activity  # noqa: E402

OUT = ROOT / "out" / "pt-checks"


@dataclass
class Check:
    name: str
    why: str
    do: str
    expect: str
    build: Callable[[], pktlib.Network | Activity] | None = None


def lan(seed: int = 1) -> tuple[pktlib.Network, pktlib.Device, pktlib.Device, pktlib.Device]:
    net = pktlib.new(seed=seed)
    r = net.router("R1", "2911", at=(300, 100))
    sw = net.switch("SW1", at=(300, 250))
    pc = net.pc("PC1", at=(200, 400), ip="10.0.0.10/24", gateway="10.0.0.1")
    pc["fa0"].connect(sw["fa0/1"])
    sw["g0/1"].connect(r["g0/0"])
    r["g0/0"].address = "10.0.0.1/24"
    return net, r, sw, pc


def module_while_powered() -> pktlib.Network:
    net = pktlib.new(seed=2)
    a = net.router("R1", "1841", at=(200, 200))
    b = net.router("R2", "2911", at=(500, 200))
    a.add_module("WIC-2T")
    b.add_module("HWIC-2T")
    a["se0/0/0"].connect(b["se0/0/0"])
    a["se0/0/0"].address = "10.1.1.1/30"
    b["se0/0/0"].address = "10.1.1.2/30"
    net.ping(a, b, ip="10.1.1.2", scenario="Serial link")
    return net


def vlan_names() -> pktlib.Network:
    net = pktlib.new(seed=3)
    sw = net.switch("SW1", at=(300, 200))
    sw.add_vlan(10, "A" * 32)
    sw.add_vlan(20, "B" * 33)
    sw.add_vlan(30, "C" * 200)
    sw.add_vlan(40, "HAS SPACES")
    sw.add_vlan(50, "SAME")
    sw.add_vlan(60, "SAME")
    sw.add_vlan(1, "RENAMED-DEFAULT")
    return net


def names_differing_by_case() -> pktlib.Network:
    net = pktlib.new(seed=4)
    net.router("R1", "2911", at=(200, 200))
    net.router("r1", "2911", at=(400, 200))
    net.router("R" + "x" * 63, "2911", at=(600, 200))
    return net


def odd_pc_addresses() -> pktlib.Network:
    net, _, sw, _ = lan(5)
    for i, (ip, gw) in enumerate(
        [("10.0.0.0/24", "10.0.0.1"), ("10.0.0.255/24", "10.0.0.1"), ("10.0.0.20/32", ""), ("10.0.0.1/24", "10.0.0.1")]
    ):
        pc = net.pc(f"ODD{i}", at=(100 + 120 * i, 550), ip=ip, gateway=gw)
        pc["fa0"].connect(sw[f"fa0/{i + 2}"])
    net.ping("ODD0", "R1", ip="10.0.0.1", scenario="Odd addresses")
    return net


def router_odd_addresses() -> pktlib.Network:
    net = pktlib.new(seed=6)
    r = net.router("R1", "2911", at=(300, 200))
    r["g0/0"].address = "10.0.0.0/24"
    r["g0/1"].address = "10.0.0.129/25"
    r["g0/2"].address = "10.0.0.130/25"
    return net


def l2_port_address() -> pktlib.Network:
    net = pktlib.new(seed=7)
    sw = net.switch("SW1", at=(300, 200))
    sw.config("interface fa0/1\n no switchport\n ip address 10.0.0.1 255.255.255.0")
    return net


def same_switch_loop() -> pktlib.Network:
    net = pktlib.new(seed=8)
    sw = net.switch("SW1", at=(300, 200))
    sw["fa0/1"].connect(sw["fa0/2"])
    return net


def rsa_1000() -> pktlib.Network:
    net, r, _, _ = lan(9)
    r.config("ip domain-name lab.local\nusername admin secret cisco\nline vty 0 4\n login local\n transport input ssh")
    r.generate_rsa_key(1000)
    return net


def pdu_edge_cases() -> pktlib.Network:
    net, r, sw, pc = lan(10)
    net.ping(sw, pc, ip="10.0.0.10", scenario="From a switch with no SVI")
    net.ping(pc, r, ip="10.0.0.1", scenario="Plain")
    return net


def phone_config() -> pktlib.Network:
    net = pktlib.new(seed=11)
    ph = net.phone("PH1", at=(300, 200), power_adapter=True)
    ph.config("hostname SHOULD-THIS-STICK")
    return net


def mode_lines_replayed() -> pktlib.Network:
    """pktlib now leaves exit/end/conf t out; this file has them written in by hand."""
    net, r, _, _ = lan(12)
    rc = r.running_config
    at = rc.index("interface GigabitEthernet0/1")
    r.running_config = (
        rc[: at + 1] + [" description before-exit", " exit", " ip address 10.9.9.1 255.255.255.0"] + rc[at + 1 :]
    )
    return net


def dhcp_and_static() -> pktlib.Network:
    net, r, _, pc = lan(13)
    r.config("ip dhcp pool LAN\n network 10.0.0.0 255.255.255.0\n default-router 10.0.0.1")
    p = pc["fa0"].el
    req(p, "PORT_DHCP_ENABLE").text = "true"  # both set: what does Packet Tracer do?
    return net


def bluetooth_address() -> pktlib.Network:
    net = pktlib.new(seed=14)
    lt = net.laptop("LT1", at=(300, 200))
    lt.set_ip("10.5.0.5/24", port="Bluetooth")
    return net


def far_coordinates() -> pktlib.Network:
    net = pktlib.new(seed=15)
    net.router("NEG", "2911", at=(-500, -300))
    net.router("FAR", "2911", at=(1234567.8, 100))
    net.router("MID", "2911", at=(400, 300))
    return net


def control_characters() -> pktlib.Network:
    net, r, _, _ = lan(16)
    r.config("banner motd #line one\x07bell#")
    net.profile = ("Name\twith tab", "a@example.com", "info\x01")
    return net


def dedup_rt02() -> pktlib.Network:
    return _stress("routing/rt02_ospf_areas.py")


def dedup_rt05() -> pktlib.Network:
    return _stress("routing/rt05_dual_stack_gre.py")


def _stress(rel: str) -> pktlib.Network:
    import runpy

    saved: dict[str, pktlib.Network] = {}
    real_save = pktlib.Network.save
    pktlib.Network.save = lambda self, path: saved.__setitem__("net", self)  # type: ignore[method-assign]
    script = ROOT / "stress" / rel
    sys.path.insert(0, str(script.parent))  # the stress scripts import their _common
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.path.remove(str(script.parent))
        pktlib.Network.save = real_save  # type: ignore[method-assign]
    return saved["net"]


def second_block_merged() -> pktlib.Network:
    """rt05 as it would be if a second `ipv6 router ospf 1` merged into the first."""
    net = dedup_rt05()
    for d in net:
        if not d.has_ios:
            continue
        rc = d.running_config
        heads = [i for i, line in enumerate(rc) if line == "ipv6 router ospf 1"]
        if len(heads) < 2:
            continue
        first, second = heads[0], heads[1]
        end = second + 1
        while end < len(rc) and rc[end].startswith(" "):
            end += 1
        body = rc[second + 1 : end]
        rc = rc[:second] + rc[end:]
        stop = first + 1
        while stop < len(rc) and rc[stop].startswith(" "):
            stop += 1
        d.running_config = rc[:stop] + body + rc[stop:]
    return net


def sw01_ordered() -> pktlib.Network:
    return _stress("switching/sw01_many_channels.py")


def global_lines(ios_order: bool) -> pktlib.Network:
    """SSH config as pktlib writes it (global lines after `line vty`), or moved where IOS saves them."""
    net, r, _, _ = lan(18)
    r.config(
        "ip domain-name lab.local\nusername admin secret cisco\nip ssh version 2\n"
        "line vty 0 4\n login local\n transport input ssh"
    )
    r.generate_rsa_key(1024)
    if ios_order:
        rc = r.running_config
        moved = [line for line in rc if line.startswith(("ip domain-name", "username", "ip ssh"))]
        rest = [line for line in rc if line not in moved]
        at = next(i for i, line in enumerate(rest) if line.startswith("interface "))
        r.running_config = rest[:at] + moved + ["!"] + rest[at:]
    net.ping("PC1", "R1", ip="10.0.0.1", scenario="PC1 to R1")
    return net


def every_model() -> pktlib.Network:
    net = pktlib.new(seed=17)
    for i, m in enumerate(pktlib.models()):
        net.add_device(f"M{i}", m, at=(100 + 130 * (i % 10), 100 + 130 * (i // 10)))
    return net


CHECKS = [
    Check(
        "every-model",
        "pktlib adds all 64 palette models from templates; they should load as Packet Tracer's own.",
        "Open. Click through a few of each kind (router, switch, end device, wireless, home kit).",
        "Opens with no error; every device is powered as it would be off the palette.",
        every_model,
    ),
    Check(
        "module-while-powered",
        "pktlib fits cards into a powered-on device (the GUI makes you switch it off first).",
        "Open. On R1 and R2, `show ip interface brief`. Click the 'Serial link' PDU in the scenario.",
        "Serial0/0/0 up/up on both; the ping succeeds. If a card isn't recognised, say which.",
        module_while_powered,
    ),
    Check(
        "vlan-names",
        "VLAN name limits pktlib doesn't enforce yet (it takes 200 characters).",
        "Open. On SW1, `show vlan brief`.",
        "Record which names show and how: 32 chars, 33 chars, 200 chars, spaces, two VLANs named "
        "SAME, VLAN 1 renamed. Any truncation or refusal is a rule pktlib should copy.",
        vlan_names,
    ),
    Check(
        "names-by-case",
        "pktlib allows R1 and r1 at once, and 64-character names.",
        "Open. Look at the device names on the workspace; try renaming r1 to R1 in the GUI.",
        "Record whether both load and whether Packet Tracer treats names case-insensitively.",
        names_differing_by_case,
    ),
    Check(
        "odd-pc-addresses",
        "PC addresses pktlib accepts but IOS-style checks might not: network address, broadcast, /32, "
        "the gateway's own address.",
        "Open. Look at each ODD PC's IP Configuration; click the 'Odd addresses' PDU.",
        "Record which addresses Packet Tracer keeps, changes or flags.",
        odd_pc_addresses,
    ),
    Check(
        "router-odd-addresses",
        "A network address on an interface, and two interfaces in one subnet.",
        "Open. On R1, `show ip interface brief` and `show running-config`.",
        "Record whether g0/0 kept 10.0.0.0/24 and whether g0/2 was refused for overlapping g0/1.",
        router_odd_addresses,
    ),
    Check(
        "l2-port-address",
        "`no switchport` and an address on a 2960 port, which has no routed ports on real IOS.",
        "Open. On SW1, `show running-config interface fa0/1`.",
        "Record what's left of the two lines.",
        l2_port_address,
    ),
    Check(
        "same-switch-loop",
        "A cable from one switch port to another on the same switch.",
        "Open.",
        "Record whether the file loads and whether the link comes up.",
        same_switch_loop,
    ),
    Check(
        "rsa-1000",
        "An RSA modulus that isn't a power of 2.",
        "Open. On R1, `show crypto key mypubkey rsa`; from PC1, `ssh -l admin 10.0.0.1` (password cisco).",
        "Record the modulus shown and whether SSH works.",
        rsa_1000,
    ),
    Check(
        "pdu-edge-cases",
        "A Simple PDU from a 2960 with no SVI.",
        "Open. Click both PDUs in the scenario list.",
        "Record what each shows (Successful, Failed, or refused when the file loads).",
        pdu_edge_cases,
    ),
    Check(
        "phone-config",
        "config() on a 7960 phone (pktlib lets it through; has_ios is true for the phone).",
        "Open. Look at the phone's config tab or CLI if it has one.",
        "Record whether the hostname line did anything.",
        phone_config,
    ),
    Check(
        "mode-lines",
        "`exit` written inside an interface block, then an address: pktlib now leaves exit out.",
        "Open. On R1, `show running-config interface g0/1`.",
        "If the address is NOT on g0/1, Packet Tracer replays exit as IOS does, and pktlib was right to drop it.",
        mode_lines_replayed,
    ),
    Check(
        "dhcp-and-static",
        "A PC with DHCP on and a static address at once.",
        "Open. Look at PC1's IP Configuration; `ipconfig` on its desktop.",
        "Record which one wins.",
        dhcp_and_static,
    ),
    Check(
        "bluetooth-address",
        "set_ip on a laptop's Bluetooth port.",
        "Open. Look at LT1's IP Configuration for Bluetooth.",
        "Record whether the address shows there.",
        bluetooth_address,
    ),
    Check(
        "far-coordinates",
        "Negative and very large positions (pktlib writes 1234567.8, never 1.23457e+06).",
        "Open. Zoom out; find NEG and FAR.",
        "Record where they land and whether the file loads at all.",
        far_coordinates,
    ),
    Check(
        "control-characters",
        "A BEL in a banner, a tab and a control character in the user profile.",
        "Open. On R1, `show banner motd`; Options > User Profile.",
        "Record what shows, and whether the file loads.",
        control_characters,
    ),
    Check(
        "rt02-deduplicated",
        "pktlib now keeps a command entered twice in a block once; rt02 lost a duplicate `network` line.",
        "Open. On STB1, `show ip ospf neighbor` and `show ip route ospf`.",
        "Neighbours FULL and the inter-area routes there, as in the original check.",
        dedup_rt02,
    ),
    Check(
        "rt05-deduplicated",
        "rt05 lost a duplicate `no auto-summary`.",
        "Open. On V6-B, `show ipv6 route` and `show ip route eigrp`.",
        "OSPFv3 and EIGRP routes learned, as in the original check.",
        dedup_rt05,
    ),
    Check(
        "rt05-blocks-merged",
        "If a second `ipv6 router ospf 1` merges into the first (as IOS would), pktlib can make config "
        "fully idempotent.",
        "Open. On V6-A and V6-B, `show running-config | section ipv6 router` and `show ipv6 route ospf`.",
        "One block each, and the OSPFv3 routes still learned. If so, the merge goes in.",
        second_block_merged,
    ),
    Check(
        "sw01-port-channels-in-order",
        "pktlib now writes Port-channel blocks in number order (Po1, Po2, ...); sw01 had them reversed "
        "when it was checked.",
        "Open. On CORE1 and CORE2, `show etherchannel summary`.",
        "All five channels (SU) on CORE1 and three on CORE2, as in the original check.",
        sw01_ordered,
    ),
    Check(
        "global-lines-pktlib-order",
        "pktlib writes `username`, `ip domain-name` and `ip ssh version 2` after `line vty`; IOS saves "
        "them near the top. Compare with the next file.",
        "Open. From PC1, `ssh -l admin 10.0.0.1` (password cisco). On R1, `show running-config`.",
        "SSH works. Note where Packet Tracer shows those lines after it loads the file.",
        lambda: global_lines(ios_order=False),
    ),
    Check(
        "global-lines-ios-order",
        "The same router with those lines where IOS saves them.",
        "Same as the previous check.",
        "SSH works. If both work, pktlib can switch to IOS order; if only one does, that's the order to use.",
        lambda: global_lines(ios_order=True),
    ),
    Check(
        "pc-ipv6-sample",
        "pktlib can't set a PC's IPv6 address yet: the template's IPV6_ADDRESSES list is empty, so the "
        "format of an entry is unknown.",
        "In Packet Tracer itself: add a PC-PT, set IPv6 Configuration to Static, address "
        "2001:db8:1::10/64, gateway 2001:db8:1::1; add a second PC set to Automatic (SLAAC). Save as "
        "pc-ipv6.pkt.",
        "Send pc-ipv6.pkt back: its XML shows how to write IPv6 on end devices.",
    ),
    Check(
        "hub-card-removed",
        "pktlib refuses to pull a middle card from a Hub-PT because it doesn't know the names after.",
        "In Packet Tracer itself: add a Hub-PT, power it off, remove the card in the third slot, power on, "
        "and hover over the hub to read its port names. Same for a Switch-PT.",
        "Record the port names, in order.",
    ),
    Check(
        "ccna-examples",
        "19 CCNA examples, built and audited but never opened in Packet Tracer.",
        "Run `uv run python scripts/examples.py build`. Open each out/examples/ccna/*.pkt, follow the "
        "'Check in Packet Tracer' list in its script's docstring, and click every scenario in the PDU list.",
        "Every scenario does what its name says (the ones named 'should FAIL' fail). Note each one that "
        "doesn't, with the example's name.",
    ),
    Check(
        "fault-lab",
        "From TODO.md: the fault lab has never been opened.",
        "Run `uv run python examples/labs/fault_lab.py`, open fault_lab.pkt and fault_lab_solution.pkt.",
        "Student file: Sales2 can't reach Sales1, Tech1 can't reach its gateway. Solution: every PDU "
        "in the scenarios succeeds.",
    ),
    Check(
        "enterprise-link-local",
        "From TODO.md: cloned PCs now get their own IPv6 link-local.",
        "Run `uv run python examples/showcase/enterprise.py`, open it, `ipconfig` on STAFF1.",
        "Link-local FE80::202:BAFF:FE64:6A24, not FE80::290:CFF:FEC7:8E5A.",
    ),
]


# --- round 3: issues #8 to #11 and what PR #6 left unseen (22 Nov 2026) -----------


def vtp_twice() -> pktlib.Network:
    net = pktlib.new(seed=30)
    sw = net.switch("SW1", at=(300, 200))
    sw.config(["vtp domain LAB", "vtp password one"])
    sw.config(["vtp password two"])
    return net


def on_a_stick(configured: bool) -> pktlib.Network:
    net = pktlib.new(seed=31)
    r = net.router("R1", "2901", at=(300, 100))
    sw = net.switch("SW1", at=(300, 250))
    pc1 = net.pc("PC1", at=(200, 400), ip="10.0.10.10/24", gateway="10.0.10.1")
    pc2 = net.pc("PC2", at=(400, 400), ip="10.0.20.10/24", gateway="10.0.20.1")
    pc1["fa0"].connect(sw["fa0/1"])
    pc2["fa0"].connect(sw["fa0/2"])
    r["g0/1"].connect(sw["g0/1"])
    sw.config(
        [
            "vlan 10",
            " name STAFF",
            "vlan 20",
            " name GUEST",
            "interface FastEthernet0/1",
            " switchport mode access",
            " switchport access vlan 10",
            "interface FastEthernet0/2",
            " switchport mode access",
            " switchport access vlan 20",
            "interface GigabitEthernet0/1",
            " switchport mode trunk",
        ]
    )
    if configured:
        r.config(["interface GigabitEthernet0/1", " no shutdown"])
        for tag in (10, 20):
            r.config(
                [
                    f"interface GigabitEthernet0/1.{tag}",
                    f" encapsulation dot1Q {tag}",
                    f" ip address 10.0.{tag}.1 255.255.255.0",
                ]
            )
    net.ping(pc1, pc2, scenario="PC1 to PC2")
    return net


def on_a_stick_activity() -> Activity:
    answer, start = on_a_stick(True), on_a_stick(False)
    return make_activity(
        answer, start, diff_items(answer, start), "Configure router-on-a-stick on R1.", tests=[("PC1", "PC2")]
    )


def access_port(configured: bool) -> pktlib.Network:
    net = pktlib.new(seed=32)
    sw = net.switch("SW1", at=(300, 200))
    if configured:
        sw.config(["interface FastEthernet0/5", " switchport mode access"])
    return net


def access_port_activity() -> Activity:
    answer, start = access_port(True), access_port(False)
    return make_activity(answer, start, diff_items(answer, start), "Make Fa0/5 on SW1 an access port.")


def flash_folders() -> pktlib.Network:
    net = pktlib.new(seed=33)
    for i, (kind, model) in enumerate((("router", "2901"), ("switch", "2960-24TT"), ("switch", "3650-24PS"))):
        d = getattr(net, kind)(f"D{i + 1}", model, at=(150 + 200 * i, 200))
        d.mkdir("ipsdir")
    return net


def short_passwords() -> pktlib.Network:
    net = pktlib.new(seed=34)
    r = net.router("R1", "2901", at=(200, 200))
    sw = net.switch("SW1", at=(450, 200))
    r.config(
        [
            "security passwords min-length 10",
            "line con 0",
            " password cisco",
            "line aux 0",
            " password cisco",
            "line vty 0 4",
            " password 7 0822455D0A16",
        ]
    )
    sw.config(["security passwords min-length 10", "line con 0", " password cisco", "line vty 0 4", " password cisco"])
    return net


CHECKS_3 = [
    Check(
        "vtp-password",
        "Issue #8: pktlib now keeps one `vtp password` line (the last). Real IOS keeps VTP settings in "
        "vlan.dat, not the running config, so it's not known whether Packet Tracer saves the line at all.",
        "Open. On SW1: `show vtp password`, `show vtp status`, `show running-config | include vtp`. Then in "
        "config mode `vtp password three`, `end`, `copy running-config startup-config`, File > Save As "
        "vtp-pt.pkt. Run `uv run pktlib show vtp-pt.pkt` (or decode it) and look for `vtp` lines in SW1's "
        "running and startup config.",
        "`show vtp password` prints `two`. Record whether Packet Tracer's own save has `vtp password three` "
        "(and `vtp domain`) in the running config. Send vtp-pt.pkt back with RECENT_FILES emptied.",
        vtp_twice,
    ),
    Check(
        "on-a-stick-answer",
        "Issue #9: the answer network of the next check. pktlib writes each new sub-interface block after "
        "`line vty`, not under its parent as IOS saves it, so it's worth seeing it work.",
        "Open. On R1: `show ip interface brief`, `show running-config`. Click the 'PC1 to PC2' PDU.",
        "G0/1.10 and G0/1.20 up/up with their addresses; the ping succeeds. Note where Packet Tracer shows "
        "the sub-interface blocks in `show running-config`.",
        lambda: on_a_stick(True),
    ),
    Check(
        "on-a-stick-activity",
        "Issue #9: diff_items now grades sub-interface lines and the parent's `no shutdown` as Running "
        "Configuration items. Not yet seen in Packet Tracer: whether Check Results grades an item under "
        "`interface GigabitEthernet0/1.10`, and whether the Activity Wizard lists sub-interfaces under Ports. "
        "Each line item carries the answer's line number (`078 interface GigabitEthernet0/1.10`), and the "
        "answer has the sub-interfaces after `line vty` while a student's IOS puts them under G0/1: if "
        "Check Results matches by position, a right answer fails, and config() must place them as IOS does.",
        "Open as a student. Check Results: note every item and whether it's Correct. Configure R1 one line "
        "at a time (`interface g0/1`, `no shutdown`, `interface g0/1.10`, `encapsulation dot1Q 10`, `ip "
        "address 10.0.10.1 255.255.255.0`, then the same for .20), checking results after each. Then open "
        "the Activity Wizard (no password) > Answer Network and look under R1 > Ports for "
        "GigabitEthernet0/1.10.",
        "0% at the start, each item turns Correct as its line goes in, 100% and the connectivity test "
        "Correct at the end. Record whether the wizard's Ports list has the sub-interfaces, and what leaves "
        "they show (IP Address, Subnet Mask?).",
        on_a_stick_activity,
    ),
    Check(
        "access-port-activity",
        "Issue #10: diff_items now grades `switchport mode access` as a line when the start leaves the port "
        "unset, because Port Mode shows 1 for both.",
        "Open as a student. Check Results. Then on SW1 `interface fa0/5`, `switchport mode trunk`, Check "
        "Results; then `switchport mode access`, Check Results.",
        "Incorrect, Incorrect (trunk), Correct (access). Note the item's name as Check Results shows it.",
        access_port_activity,
    ),
    Check(
        "spaced-device-name",
        'Issue #11: pktlib refuses `net.switch("Switch 7")`. Nothing is known about what Packet Tracer '
        "does with a space in a name, so nothing changes until this is seen.",
        "In Packet Tracer itself: add a 2960 and a PC-PT. Config tab > Display Name: `Switch 7` and `PC 7`. "
        "Also try a name with each of `. ( ) # / &` and a 70-character name. On the switch CLI, `hostname "
        "Switch 7`. Save as spaced-name.pkt, empty RECENT_FILES, then `uv run pktlib show spaced-name.pkt`.",
        "Record: which names the Display Name box accepts; what the CLI hostname becomes (and whether the "
        "display name follows it); what pktlib says when loading the file. Send spaced-name.pkt back for "
        "tests/fixtures.",
    ),
    Check(
        "flash-folders",
        "PR #6: `mkdir()` was only seen working as a hand-written folder placed first on a 2901. This file "
        "has `ipsdir` made by `mkdir()` on a 2901 (D1), a 2960 (D2) and a 3650 (D3).",
        "Open. On each: `dir flash:`. On D1 also `mkdir flash:ipsdir/inner` and `dir flash:ipsdir`, and "
        "save the file as folders-pt.pkt.",
        "`ipsdir` listed as `drw-`, size 192, on each. Record any that refuse or don't list it, and whether "
        "a folder inside a folder works on D1. Send folders-pt.pkt back.",
        flash_folders,
    ),
    Check(
        "short-passwords",
        "PR #6: only a plain VTY password on a 2901 was seen dropped on reload under min-length 10. This file "
        "has short passwords on R1's con, aux and VTY (`password 7` form) and SW1's con and VTY.",
        "Open. On R1 and SW1: `show running-config | section line`. Then `copy running-config "
        "startup-config`, `reload`, and the same `show` again.",
        "Record, for each line block, whether its password is there after opening and after the reload.",
        short_passwords,
    ),
    Check(
        "command-log",
        "Packet Tracer saves every CLI command typed, with the time and device, in COMMAND_LOGS (11 "
        "entries in tests/fixtures/rich2-answer.pkt, from 27 Oct). A file pktlib builds has none. Not "
        "known: whether the GUI shows this log anywhere, so whether a lecturer marking a file would see it.",
        "Open tests/fixtures/rich2-answer.pkt. Look through the menus (Extensions, Tools, View, Options) "
        "and each device's window for anything called a command log or history. Then type a few commands "
        "on R1 (`enable`, `show ip interface brief`), save as command-log-pt.pkt, and run `uv run python "
        "-c \"import pktlib, xml.etree.ElementTree as E; x = E.fromstring(pktlib.decode(open('command-log-pt.pkt', "
        "'rb').read())); print(len(x.findall('COMMAND_LOGS/LOG_ENTRY')))\"`. Also open a .pka from this "
        "round as a student, type a command, and check the same menus in the activity window.",
        "Record where the log shows (menu path, screenshot) or that it doesn't; whether it lists the ISP "
        "commands from 27 Oct; and the count before and after your commands. Delete command-log-pt.pkt "
        "after: it's a scratch file.",
    ),
]

ROUNDS = {1: (CHECKS, OUT), 3: (CHECKS_3, ROOT / "out" / "pt-checks-3")}


def main() -> None:
    checks, out = ROUNDS[int(sys.argv[1]) if len(sys.argv) > 1 else 1]
    out.mkdir(parents=True, exist_ok=True)
    rel = out.relative_to(ROOT).as_posix()
    lines = [
        "# Packet Tracer checks",
        "",
        "Packet Tracer 8.2.0 (build 8.2.0.0162). For each: open the file (or do the steps), do what it",
        "says, and fill in **Result** with what Packet Tracer did, word for word where it shows text.",
        "Note anything unexpected even if it isn't asked about. Screenshots welcome.",
        "",
    ]
    for i, c in enumerate(checks, 1):
        stem = f"{i:02d}-{c.name}"
        where = "no file"
        if c.build is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", pktlib.PktWarning)
                    built = c.build()
                    name = f"{stem}.pka" if isinstance(built, Activity) else f"{stem}.pkt"
                    built.save(out / name)
                where = f"`{rel}/{name}`"
            except pktlib.PktError as e:
                where = f"not built: pktlib refuses it ({e}); skip, or try it by hand in the GUI"
        lines += [
            f"## {i}. {c.name} ({where})",
            "",
            f"- **Why:** {c.why}",
            f"- **Do:** {c.do}",
            f"- **Expect:** {c.expect}",
            "- **Result:**",
            "",
        ]
    (out / "CHECKS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {sum(c.build is not None for c in checks)} files and CHECKS.md to {out}")


if __name__ == "__main__":
    main()
