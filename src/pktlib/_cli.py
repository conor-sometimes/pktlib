"""pktlib command line.

pktlib decode  in.pkt  [out.xml]     .pkt -> Packet Tracer XML
pktlib encode  in.xml  out.pkt       XML -> .pkt
pktlib info    in.pkt                devices, ports in use, links, addresses
pktlib audit   in.pkt                what's wrong that can be seen in the file (exit 1 if anything)
pktlib dump    in.pkt  [out.py]      .pkt -> a Python script that rebuilds it
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._audit import audit
from ._codec import decode, encode
from ._errors import PktError
from ._export import to_python
from ._model import Network, load


def _out(path: str | None, data: bytes | str) -> None:
    if path is None:
        sys.stdout.write(data if isinstance(data, str) else data.decode("utf-8", "replace"))
    elif isinstance(data, str):
        Path(path).write_text(data, encoding="utf-8")
    else:
        Path(path).write_bytes(data)


def _info(path: str) -> str:
    net = load(path, strict=False)  # reading only: say what it is, whatever version
    edition = f"edition {net.edition}" if net.edition else "an edition pktlib doesn't know"
    lines = [f"Packet Tracer {net.version} ({edition})", ""]
    for d in net.devices:
        x, y = d.xy
        lines.append(f"{d.name}  {d.kind} {d.model}  at {x:g},{y:g}")
        for p in d.ports.values():
            link = p.link
            if link is None and not p.ip:
                continue
            addr = f" {p.address}" if p.address else ""
            peer = ""
            if link is not None:
                other = link.other(p)
                peer = f"  -> {other.device.name}.{other.name} ({link.cable})"
            lines.append(f"  {p.name}{addr}{peer}")
        if not d.has_ios and d.gateway:
            lines.append(f"  gateway {d.gateway}")
    return "\n".join(lines) + "\n"


def _audit_files(paths: list[str]) -> int:
    """Audit each file; exit 1 if any has a problem or can't be read."""
    bad = 0
    for path in paths:
        try:
            found = audit(load(path))
        except PktError as e:
            print(f"pktlib: {path}: {e}", file=sys.stderr)
            bad += 1
            continue
        except OSError as e:
            print(f"pktlib: {path}: {e.strerror or e}", file=sys.stderr)
            bad += 1
            continue
        lines = "".join(f"  x {p}\n" for p in found)
        _out(None, lines + (f"{len(found)} problem(s) in {path}\n" if found else f"{path}: nothing found\n"))
        bad += bool(found)
    if len(paths) > 1:
        _out(None, f"{len(paths) - bad} of {len(paths)} files clean\n")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    """Run the command line; returns the exit code."""
    ap = argparse.ArgumentParser(prog="pktlib", description="Work with Cisco Packet Tracer .pkt files.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, nargs in (("decode", "?"), ("dump", "?")):
        p = sub.add_parser(name)
        p.add_argument("src")
        p.add_argument("dst", nargs=nargs)
    p = sub.add_parser("encode")
    p.add_argument("src")
    p.add_argument("dst")
    sub.add_parser("info").add_argument("src")
    sub.add_parser("audit").add_argument("src", nargs="+")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "decode":
            _out(args.dst, decode(Path(args.src).read_bytes()))
        elif args.cmd == "encode":
            xml = Path(args.src).read_bytes()
            Network.from_xml(xml, strict=False)  # refuse XML Packet Tracer couldn't open
            _out(args.dst, encode(xml))
        elif args.cmd == "info":
            _out(None, _info(args.src))
        elif args.cmd == "audit":
            return _audit_files(args.src)
        elif args.cmd == "dump":
            out = Path(args.dst).with_suffix(".pkt").name if args.dst else "out.pkt"
            _out(args.dst, to_python(load(args.src), out))
    except BrokenPipeError:  # `pktlib decode x.pkt | head`: the reader left, nothing to report
        sys.stderr.close()
        return 0
    except PktError as e:
        print(f"pktlib: {args.src}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"pktlib: {e.filename or args.src}: {e.strerror or e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001  a bug in pktlib: say so, without a wall of traceback
        print(
            f"pktlib: {args.src}: internal error ({type(e).__name__}: {e}). Please report it at "
            f"https://github.com/conor-sometimes/pktlib/issues",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
