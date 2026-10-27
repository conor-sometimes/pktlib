"""Network -> a Python script that rebuilds it with pktlib's API."""

from __future__ import annotations

import functools
import keyword
import re

from ._errors import PktError
from ._iosconfig import blocks, interesting_config, interfaces
from ._model import GUI_ONLY_KINDS, SPEC, Device, Network
from ._model import new as pktlib_new


def _ident(name: str, taken: set[str]) -> str:
    v = re.sub(r"\W", "_", name)
    if not v or v[0].isdigit() or keyword.iskeyword(v) or v in ("net", "pktlib", "sys"):
        v = "d_" + v
    base, i = v, 2
    while v in taken:
        v, i = f"{base}_{i}", i + 1
    taken.add(v)
    return v


def _fitted(d: Device) -> dict[tuple[int, ...], str]:
    """Slot path -> model of each removable module fitted."""
    return {s.path: s.model for s in d.slots if s.removable and s.model is not None}


@functools.cache
def _factory_up(model: str) -> dict[str, bool]:
    """Interface -> whether it's up on a brand-new device (switch ports are, router ports aren't)."""
    try:
        return {
            name: up
            for name, (_, _, up) in interfaces(
                pktlib_new().add_device("X", model, unverified=True).running_config
            ).items()
        }
    except PktError:
        return {}


@functools.cache
def _factory_vlans(model: str) -> dict[int, str]:
    """The VLAN database a brand-new device of this model comes with."""
    try:
        return dict(pktlib_new().add_device("X", model, unverified=True).vlans)
    except PktError:
        return {}


@functools.cache
def _factory_modules(model: str) -> dict[tuple[int, ...], str]:
    """The modules a brand-new device of this model comes with."""
    try:
        return _fitted(pktlib_new().add_device("X", model, unverified=True))
    except PktError:
        return {}


@functools.cache
def _factory(model: str) -> tuple[frozenset[str], dict[str, tuple[str, ...]]]:
    """What a brand-new device of this model already has: its top-level one-line
    commands, and its blocks (header -> body), so an export leaves them out."""
    try:
        fresh = pktlib_new().add_device("X", model, unverified=True)
    except PktError:
        return frozenset(), {}
    singles = frozenset(
        line
        for line in fresh.running_config
        if line and not line.startswith((" ", "!", "hostname", "interface ", "router ", "line "))
    )
    return singles, {header: tuple(body) for header, body in blocks(interesting_config(fresh.running_config)) if body}


def _num(x: float) -> str:
    return f"{x:g}"


def to_python(net: Network, out: str = "out.pkt") -> str:
    """Python source that builds an equivalent network and saves it to `out`.
    Positions, fitted modules, cables, PC addresses and every non-default line
    of IOS config come across; the rest is Packet Tracer's own defaults."""
    lines = [
        f'"""Rebuilds a Packet Tracer {net.version} network. Run: python this.py"""',
        "import pktlib",
        "",
        "net = pktlib.new()",
        "",
    ]
    var: dict[str, str] = {}
    taken: set[str] = set()
    model_of: dict[str, str] = {}
    helper = {"PC-PT": "pc", "Laptop-PT": "laptop", "Server-PT": "server", "Printer-PT": "printer"}
    for d in net.devices:
        x, y = d.xy
        at = f"at=({_num(x)}, {_num(y)})"
        model = d.model
        if d.kind == "Router" and model == "1841" and any(p.startswith("Serial") for p in d.ports):
            model = "1841+WIC-2T"
        if model in helper:
            addr = next((p.address for p in d.ports.values() if p.address), None)
            extra = f", ip={addr!r}" if addr else ""
            extra += f", gateway={d.gateway!r}" if addr and d.gateway else ""
            call = f"net.{helper[model]}({d.name!r}, {at}{extra})"
        elif model in SPEC:
            flag = "" if SPEC[model]["verified"] else ", unverified=True"
            call = f"net.add_device({d.name!r}, {model!r}, {at}{flag})"
        else:
            lines.append(f"# skipped {d.name}: {d.kind} {d.model} isn't in pktlib's spec")
            continue
        var[d.name] = _ident(d.name, taken)
        model_of[d.name] = model
        lines.append(f"{var[d.name]} = {call}")
        # cards taken out of or added to what the model comes with, outermost slot first
        have, factory = _fitted(d), _factory_modules(model)
        for path in sorted(p for p in factory if have.get(p) != factory[p]):
            lines.append(f"{var[d.name]}.remove_module({path!r})")
        for path in sorted(p for p in have if have[p] != factory.get(p)):
            lines.append(f"{var[d.name]}.add_module({have[path]!r}, slot={path!r})")
        # the VLAN database: what was added, renamed or taken out
        vlans, default_vlans = dict(d.vlans), _factory_vlans(model)
        for v in sorted(set(default_vlans) - set(vlans)):
            lines.append(f"{var[d.name]}.remove_vlan({v})")
        for v in sorted(vlans):
            if default_vlans.get(v) != vlans[v]:
                lines.append(f"{var[d.name]}.add_vlan({v}, {vlans[v]!r})")
        # end devices that take their address from DHCP
        if not d.has_ios:
            for p in d:
                if p.el.findtext("PORT_DHCP_ENABLE") == "true":
                    lines.append(f"{var[d.name]}.use_dhcp({p.name!r})")

    links = []
    for link in net.links:
        (a, ap), (b, bp) = link.ends
        if a not in var or b not in var:
            continue
        if link.cable == "serial" and link.dce and link.dce[0] == b:
            a, ap, b, bp = b, bp, a, ap
        auto = net.auto_cable(net.device(a).port(ap), net.device(b).port(bp))
        cable = "" if link.cable == auto else f", cable={link.cable!r}"
        note = "  # serial: this end is DCE" if link.cable == "serial" else ""
        links.append(f"{var[a]}[{ap!r}].connect({var[b]}[{bp!r}]{cable}){note}")
    if links:
        lines += [""] + links

    for d in net.devices:
        if d.name not in var or not d.has_ios or d.kind in GUI_ONLY_KINDS:
            continue  # home routers keep IOS text pktlib can't write back: their GUI sets them up
        default_lines, default_blocks = _factory(model_of[d.name])
        default_up = _factory_up(model_of[d.name])
        now_up = {name: up for name, (_, _, up) in interfaces(d.running_config).items()}
        cfg: list[str] = []
        for header, body in blocks(interesting_config(d.running_config)):
            if header.startswith("interface "):
                # shutdown or no shutdown only where it differs from what the model starts with
                name = header.split(None, 1)[1]
                body = [b for b in body if b not in ("shutdown", "no shutdown")]
                if now_up.get(name, True) != default_up.get(name, False):
                    body.append("no shutdown" if now_up.get(name, True) else "shutdown")
            if not body:
                if header.startswith(("interface ", "router ", "line ")) or header not in default_lines:
                    cfg.append(header)
                continue
            # a block the model starts with: only what was added to it (replaying the
            # whole block would merge into the default one and repeat its lines)
            added = [b for b in body if b not in default_blocks.get(header, ())]
            if added or header not in default_blocks:
                cfg += [header] + [" " + b for b in added]
        if d.hostname not in (d.name, "Router", "Switch"):
            cfg.insert(0, f"hostname {d.hostname}")
        if cfg:
            text = "\n".join(c.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') for c in cfg)
            lines += ["", f'{var[d.name]}.config("""\n{text}\n""")']

    drawings = []
    for sh in net.shapes:
        x1, y1, x2, y2 = (_num(v) for v in sh.box)
        args = f"{x1}, {y1}, {x2}, {y2}, outline={sh.outline!r}" + (f", fill={sh.fill!r}" if sh.fill else "")
        drawings.append(f"net.{sh.kind}({args})")
    for n in net.notes:
        x, y = n.xy
        if any(c in n.html for c in "&<>"):  # kept exactly as stored
            drawings.append(f"net.note({n.html!r}, at=({_num(x)}, {_num(y)}), html=True)")
        else:
            drawings.append(f"net.note({n.text!r}, at=({_num(x)}, {_num(y)}))")
    if drawings:
        lines += [""] + drawings

    pings = [
        f"net.ping({var[p.source]}, {var[p.destination]}, ip={p.ip!r}, scenario={p.scenario!r})"
        for p in net.pdus
        if p.source in var and p.destination in var
    ]
    if pings:
        lines += ["", "# ping checks (Simple PDUs), listed under the workspace"] + pings
    if any(net.profile):
        lines += ["", f"net.profile = {tuple(net.profile)!r}"]

    lines += ["", f"net.save({out!r})", ""]
    return "\n".join(lines)
