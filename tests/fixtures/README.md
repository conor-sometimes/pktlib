# Where every sample file came from

Every `.pkt` and `.pka` in the repo is one of ours: a network pktlib built, or one
saved in Packet Tracer 8.2 for a check. No file from a course (a lecturer's starter
file, an assessment, a NetAcad activity) is ever committed: read one for its quirks,
pin the quirk in a test, keep the file out. `tests/test_model.py` fails on a sample
file missing from this list.

## scripts/sources/

- `catalogue_network.pkt`: one of every network device, fresh off the palette, saved by Packet Tracer 8.2.
- `catalogue_end.pkt`: one of every end device, fresh off the palette, saved by Packet Tracer 8.2.
- `modules.pkt`: devices with their modules fitted in the Physical tab, saved by Packet Tracer 8.2.
- `wic2t.pkt`: one 1841 with a WIC-2T in slot 0, made and saved in Packet Tracer 8.2 (round 2, 1b).
- `activity.pka`: a 2911 and a PC, five items ticked in Packet Tracer 8.2's Activity Wizard (round 1).

## tests/fixtures/

- `routed.pkt`: built by `scripts/sources/routed.py`, opened and saved by Packet Tracer 8.2 (round 2, 1a).
- `pc-ipv6.pkt`: two pktlib PCs given IPv6 in Packet Tracer 8.2's IP Configuration (round 1, 23).
- `hub-card-removed.pkt`: a pktlib Hub-PT and Switch-PT with a card pulled in Packet Tracer 8.2 (round 1, 24).
- `sample-answer.pkt`: a pktlib 2911 and PC (round 1, 28).
- `sample.pka`: made from `sample-answer.pkt` in Packet Tracer 8.2's Activity Wizard (round 1, 28).
- `rich-answer.pkt`, `rich-start.pkt`: pktlib-built VLAN and OSPF networks saved by Packet Tracer 8.2 (round 1).
- `rich.pka`: made from those two in Packet Tracer 8.2's Activity Wizard (round 1).
- `rich2-answer.pkt`, `rich2-start.pkt`: built by `scripts/sources/rich2.py`, saved by Packet Tracer 8.2 (round 2, 3a).
- `rich2.pka`: made from those two in Packet Tracer 8.2's Activity Wizard (round 2, 3b).
- `locked-a.pka`, `locked-b.pka`: `sample-answer.pkt` as an activity with throwaway passwords alpha1 and bravo2 (round 2, 4).

The rounds are written up in `pt-results/CHECKS.md` (round 1) and `CHECKS-2.md` (round 2).
