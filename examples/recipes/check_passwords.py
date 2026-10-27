"""Check every device's passwords against the ones a lab brief asked for, hashed or not.

    uv run python examples/recipes/check_passwords.py        # checks sample.pkt
    uv run python examples/recipes/check_passwords.py lab.pkt

Shows: walking `device.running_config` line by line, remembering which `line`
block a password sits in, and `pktlib.password_matches(stored, password)`,
which reads plain text, type 7 (`password 7 0822455D0A16`) and type 5
(`secret 5 $1$...`) the way IOS stores them, so it works on files where
`service password-encryption` is on.
"""

import sys

import pktlib

# what the brief asked for: where -> the password
EXPECTED = {
    "enable secret": "class",
    "line con 0": "cisco",
    "line vty 0 4": "cisco",
}


def sample() -> pktlib.Network:
    """Three routers: one right, one with a wrong vty password, one with no enable secret.
    The hashes are what IOS saves: type 5 for 'class', type 7 for 'cisco'."""
    net = pktlib.new(seed=8)
    configs = {
        "R1": "enable secret 5 $1$mERr$9cTjUIEqNGurQiFU.ZeCi1\n"
        "line con 0\n password 7 0822455D0A16\n login\nline vty 0 4\n password cisco\n login",
        "R2": "enable secret 5 $1$mERr$9cTjUIEqNGurQiFU.ZeCi1\n"
        "line con 0\n password cisco\n login\nline vty 0 4\n password cisco123\n login",
        "R3": "line con 0\n password cisco\n login\nline vty 0 4\n password cisco\n login",
    }
    for i, (name, cfg) in enumerate(configs.items()):
        r = net.router(name, "1941", at=(150 + 200 * i, 100))
        r.config(cfg)
        pc = net.pc(f"PC{i + 1}", at=(150 + 200 * i, 250), ip=f"10.0.{i}.10/24", gateway=f"10.0.{i}.1")
        r["g0/0"].connect(pc["fa0"])
        r["g0/0"].address = f"10.0.{i}.1/24"
        net.ping(pc, r, scenario="PCs to their routers")
    net.save("sample.pkt")
    return net


def passwords(device: pktlib.Device) -> dict[str, str]:
    """Where -> stored password, e.g. {'enable secret': '5 $1$...', 'line vty 0 4': 'cisco'}."""
    found, block = {}, None
    for line in device.running_config:
        if not line.startswith(" "):
            block = line if line.startswith("line ") else None
        if line.startswith(("enable secret ", "enable password ")):
            found[" ".join(line.split()[:2])] = line.split(None, 2)[2]
        elif block and line.startswith(" password "):
            found[block] = line.split(None, 1)[1]
    return found


net = pktlib.load(sys.argv[1]) if len(sys.argv) > 1 else sample()

for device in net:
    if not device.has_ios or device.kind not in ("Router", "Switch", "MultiLayerSwitch"):
        continue
    stored = passwords(device)
    for where, wanted in EXPECTED.items():
        if where not in stored:
            verdict = "MISSING"
        elif pktlib.password_matches(stored[where], wanted):
            verdict = "ok"
        else:
            verdict = f"WRONG (stored as {stored[where]!r})"
        print(f"{device.name:6} {where:14} {verdict}")
