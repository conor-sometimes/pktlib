"""Build the template pktlib writes activities (.pka) from.

    uv run python scripts/make_activity_template.py

Source: scripts/sources/activity.pka, made in Packet Tracer 8.2's Activity
Wizard on 27 Oct 2026 (a 2911 and a PC, five items ticked). Everything but
the networks, the two assessment trees and the instruction text is kept as
Packet Tracer wrote it. Writes src/pktlib/data/activity.xml.gz.
"""

from __future__ import annotations

import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pktlib._codec import decode  # noqa: E402
from pktlib._xml import req  # noqa: E402


def main() -> None:
    root = ET.fromstring(decode((ROOT / "scripts" / "sources" / "activity.pka").read_bytes()))
    # Packet Tracer saves the paths of the files it last opened in every file, so the
    # template maker's username and folders would end up in every activity
    for recent in root.iter("RECENT_FILES"):
        for c in list(recent):
            recent.remove(c)
    for net in root.findall("PACKETTRACER5"):
        net.clear()  # filled from pktlib networks when an activity is written
    for tree in ("COMPARISONS", "INITIALSETUP"):
        t = req(root, tree)
        for node in t.findall("NODE"):
            t.remove(node)
    for page in root.iterfind("ACTIVITY/INSTRUCTIONS/PAGE"):
        page.text = ""
    req(root, "ACTIVITY").set("ELAPSED", "0")
    out = ROOT / "src" / "pktlib" / "data" / "activity.xml.gz"
    out.write_bytes(gzip.compress(ET.tostring(root, encoding="utf-8"), mtime=0))
    print("wrote", out)


if __name__ == "__main__":
    main()
