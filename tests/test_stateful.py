"""Random networks built through the public API, checked after every step.

Hypothesis drives a sequence of calls (add devices, cable them, address and configure them,
VLANs, modules, licences, SSH keys, renames, removals, pings, drawings, save and reload,
export to Python and rebuild), with good arguments and bad ones. A shadow model keeps the
device names and the number of cables the calls should have left. After every step:

- the network still saves (every step snapshots it), and its device names and cable count
  match the shadow;
- a call that was refused left the XML exactly as it was;
- names are unique, every cable joins two ports that know each other, no port has two
  cables, and every address reads back;
- the audit runs to the end.

`just test` runs a few dozen sequences; PKTLIB_SCALE multiplies that, and `just soak`
runs it on every core for as long as you let it, each sequence a network nobody wrote. Run with
`--hypothesis-show-statistics` to see how often each call went through or was refused.
"""

from __future__ import annotations

import ipaddress
import warnings

from hypothesis import HealthCheck, event, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

import pktlib
from pktlib import PktError, PktWarning
from tests.conftest import SCALE, examples

MODELS = [
    "2911",
    "1841+WIC-2T",
    "1941",
    "ISR4331",
    "2960-24TT",
    "3560-24PS",
    "3650-24PS",
    "PC-PT",
    "Laptop-PT",
    "Server-PT",
    "7960",
    "AccessPoint-PT",
    "Hub-PT",
    "Router-PT-Empty",
    "Linksys-WRT300N",
    "Cloud-PT",
]
NAMES = st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,8}", fullmatch=True)
ODD_NAMES = st.one_of(*[NAMES] * 8, st.text(max_size=6), st.integers(), st.none())
ADDRESSES = st.builds(
    lambda a, b, n, p: f"10.{a}.{b}.{n}/{p}",
    st.integers(0, 3),
    st.integers(0, 3),
    st.integers(1, 254),
    st.sampled_from([8, 16, 24, 24, 24, 30]),
)
ODD_ADDRESSES = st.one_of(
    ADDRESSES,
    ADDRESSES,
    st.sampled_from(["10.0.0.1", "10.0.0.1/33", "nope", "300.1.1.1/24", "", "10.0.0.1 255.0.255.0"]),
    st.integers(),
)
CONFIG = st.sampled_from(
    [
        "hostname EDGE",
        "ip domain-name lab.local",
        "router ospf 1\n network 10.0.0.0 0.255.255.255 area 0",
        "interface g0/0\n description uplink\n exit",
        "interface g0/1\n ip address 10.9.9.1 255.255.255.0\n no shutdown",
        "vlan 10\n name TEN",
        "no vlan 10",
        "vlan 20-22",
        "interface fa0/1\n switchport mode access\n switchport access vlan 30",
        "interface fa0/2\n sw acc vl 40",
        "interface range fa0/3 - 4\n switchport mode trunk",
        "banner motd #hi#",
        "interface g0/1\n ip address 10.9.9.1/24",
        "conf t\nend",
        "\trouter rip\n\tnetwork 10.0.0.0",
        "vlan 99999",
        "interface",
        "line vty 0 4\n password cisco\n login",
        "router ospf 1\n default-information originate metric 10",
        "ip routing",
    ]
)
REFUSED = (PktError, TypeError)


class Networks(RuleBasedStateMachine):
    @initialize(seed=st.integers(0, 2**16), models=st.lists(st.sampled_from(MODELS), min_size=2, max_size=5))
    def start(self, seed, models):
        """A few devices to start from, so most steps work on a real network."""
        self.net = pktlib.new(seed=seed)
        for i, model in enumerate(models):
            self.net.add_device(f"D{i}", model)
        self.names: set[str] = {f"D{i}" for i in range(len(models))}
        self.cables = 0

    def attempt(self, label, fn) -> bool:
        """Run one call; a refusal must leave no trace. Returns whether it went through."""
        before = self.net.to_xml()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", PktWarning)
                fn()
        except REFUSED as e:
            event(f"{label}: refused ({type(e).__name__})")
            assert self.net.to_xml() == before, f"{label} was refused but changed the network"
            return False
        event(f"{label}: ok")
        return True

    def device(self, data):
        return data.draw(st.sampled_from(list(self.net)))

    def port(self, data):
        ports = list(self.device(data))
        return data.draw(st.sampled_from(ports)) if ports else None

    # --- building -------------------------------------------------------------------------
    @rule(
        model=st.sampled_from(MODELS),
        name=ODD_NAMES,
        at=st.one_of(st.none(), st.tuples(st.integers(-50, 3000), st.integers(-50, 3000))),
    )
    def add_device(self, model, name, at):
        if self.attempt("add_device", lambda: self.net.add_device(name, model, at=at)):
            self.names.add(name)

    @rule(name=NAMES, ip=st.one_of(st.none(), ODD_ADDRESSES), gateway=st.sampled_from(["", "10.0.0.1", "nope"]))
    def add_pc(self, name, ip, gateway):
        if self.attempt("pc", lambda: self.net.pc(name, ip=ip, gateway=gateway)):
            self.names.add(name)

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), cable=st.sampled_from([None, None, None, None, "straight", "cross", "serial", "coax", ""]))
    def connect(self, data, cable):
        free = [p for d in self.net for p in d if p.link is None]
        if data.draw(st.integers(0, 3)) and len(free) >= 2:  # mostly free ports, so most cables go in
            a, b = data.draw(st.sampled_from(free)), data.draw(st.sampled_from(free))
        else:
            a, b = self.port(data), self.port(data)
        if a is None or b is None:
            return
        if self.attempt("connect", lambda: a.connect(b, cable=cable)):
            self.cables += 1

    @precondition(lambda self: len(self.net.links) >= 1)
    @rule(data=st.data())
    def disconnect(self, data):
        link = data.draw(st.sampled_from(self.net.links))
        if self.attempt("disconnect", lambda: link.ports[0].disconnect()):
            self.cables -= 1

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), addr=ODD_ADDRESSES)
    def address(self, data, addr):
        routed = [p for d in self.net if d.kind in ("Router", "Pc", "Server") for p in d if p.type != "eBluetooth"]
        p = data.draw(st.sampled_from(routed)) if routed and data.draw(st.integers(0, 3)) else self.port(data)
        if p is not None:
            self.attempt("address", lambda: setattr(p, "address", addr))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), addr=ODD_ADDRESSES, gateway=st.sampled_from(["", "10.0.0.1", "10.1.0.1", "bad"]))
    def end_device(self, data, addr, gateway):
        hosts = [d for d in self.net if d.kind in ("Pc", "Laptop", "Server")]
        d = data.draw(st.sampled_from(hosts)) if hosts and data.draw(st.integers(0, 3)) else self.device(data)
        how = data.draw(st.sampled_from(["set_ip", "gateway", "dhcp_on", "dhcp_off"]))
        if how == "set_ip":
            self.attempt("set_ip", lambda: d.set_ip(addr, gateway))
        elif how == "gateway":
            self.attempt("gateway", lambda: setattr(d, "gateway", gateway))
        else:
            self.attempt("dhcp", lambda: setattr(d, "dhcp", how == "dhcp_on"))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), text=CONFIG)
    def config(self, data, text):
        d = self.device(data)
        self.attempt("config", lambda: d.config(text))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), number=st.one_of(st.integers(-2, 4100), st.just("10")), name=st.one_of(st.none(), NAMES))
    def vlan(self, data, number, name):
        d = self.device(data)
        if data.draw(st.booleans()):
            self.attempt("add_vlan", lambda: d.add_vlan(number, name))
        else:
            self.attempt("remove_vlan", lambda: d.remove_vlan(number))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), name=ODD_NAMES)
    def rename(self, data, name):
        d = self.device(data)
        old = d.name
        if self.attempt("rename", lambda: setattr(d, "name", name)):
            self.names.discard(old)
            self.names.add(name)

    @precondition(lambda self: len(self.net) >= 1)
    @rule(
        data=st.data(),
        module=st.sampled_from(
            ["HWIC-2T", "WIC-2T", "NIM-2T", "WIC-1ENET", "AC-POWER-SUPPLY", "IP_PHONE_POWER_ADAPTER", "NOPE"]
        ),
    )
    def module(self, data, module):
        d = self.device(data)
        fitted = [s.path for s in d.slots if s.removable and not s.empty]
        if fitted and data.draw(st.booleans()):
            slot = data.draw(st.sampled_from(fitted))
            self.attempt("remove_module", lambda: d.remove_module(slot))
        else:
            self.attempt("add_module", lambda: d.add_module(module))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), bits=st.sampled_from([512, 1024, 2048, 100, "1024"]))
    def security(self, data, bits):
        d = self.device(data)
        if data.draw(st.booleans()):
            self.attempt("license", lambda: d.enable_license("securityk9"))
        else:
            self.attempt("domain", lambda: d.config("ip domain-name lab.local"))
            self.attempt("rsa_key", lambda: d.generate_rsa_key(bits))

    @precondition(lambda self: len(self.net) >= 2)
    @rule(
        data=st.data(),
        ip=st.one_of(st.none(), st.just("10.0.0.1"), st.just("bad")),
        scenario=st.sampled_from([None, "A", "B"]),
    )
    def ping(self, data, ip, scenario):
        a, b = self.device(data), self.device(data)
        self.attempt("ping", lambda: self.net.ping(a, b, ip=ip, scenario=scenario))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data(), label=st.one_of(st.none(), st.just("LAN"), st.just("  ")))
    def drawings(self, data, label):
        d = self.device(data)
        how = data.draw(st.sampled_from(["around", "rectangle", "ellipse", "note"]))
        x, y = d.xy
        if how == "around":
            self.attempt("around", lambda: self.net.around(d, label=label))
        elif how == "note":
            self.attempt("note", lambda: self.net.note(label or "x", at=(x, y)))
        else:
            draw = self.net.rectangle if how == "rectangle" else self.net.ellipse
            width = data.draw(st.integers(-5, 200))
            self.attempt(how, lambda: draw(x, y, x + width, y + 50, fill="green"))

    @rule(name=st.one_of(NAMES, st.integers()))
    def profile(self, name):
        self.attempt("profile", lambda: setattr(self.net, "profile", name))

    @precondition(lambda self: len(self.net) >= 1)
    @rule(data=st.data())
    def remove(self, data):
        d = self.device(data)
        name, cables = d.name, len(d.links)
        self.net.remove_device(d)
        assert d not in self.net
        self.names.discard(name)
        self.cables -= cables

    @rule()
    def save_and_reload(self):
        audit = pktlib.audit(self.net)
        again = pktlib.Network.from_bytes(self.net.to_bytes(), seed=0)
        assert again.to_xml() == self.net.to_xml()
        assert pktlib.audit(again) == audit
        self.net = again

    @precondition(lambda self: 1 <= len(self.net) <= 6)
    @rule()
    def export_and_rebuild(self):
        """to_python's script, run, exports the same script: nothing it covers is lost."""
        script = pktlib.to_python(self.net)
        scope: dict = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PktWarning)
            exec(compile(script.replace("net.save('out.pkt')", ""), "<export>", "exec"), scope)
        assert pktlib.to_python(scope["net"]) == script

    # --- what must always hold ------------------------------------------------------------
    @invariant()
    def matches_the_shadow(self):
        names = [d.name for d in self.net]
        assert len(names) == len(set(names))
        assert set(names) == self.names
        assert len(self.net.links) == self.cables

    @invariant()
    def cables_are_consistent(self):
        seen = set()
        for link in self.net.links:
            a, b = link.ports
            assert a.peer == b and b.peer == a
            assert a not in seen and b not in seen, "a port with two cables"
            seen |= {a, b}

    @invariant()
    def addresses_read_back(self):
        for d in self.net:
            for p in d:
                if p.address:
                    ipaddress.IPv4Interface(p.address)

    @invariant()
    def audit_runs(self):
        pktlib.audit(self.net)


Networks.TestCase.settings = settings(
    max_examples=examples(25),
    stateful_step_count=50 if SCALE > 1 else 20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
TestNetworks = Networks.TestCase
