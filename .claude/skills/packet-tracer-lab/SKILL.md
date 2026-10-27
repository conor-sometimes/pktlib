---
name: packet-tracer-lab
description: Build, check or convert a Cisco Packet Tracer lab (.pkt) with pktlib. Use when someone asks for a Packet Tracer lab, practical, exercise, topology or assignment file, wants a .pkt checked or linted, wants an answer key for one, or wants an old .pkt brought up to Packet Tracer 8.2.
---

# Packet Tracer lab

pktlib writes `.pkt` files Packet Tracer 8.2 opens. Read the repo's `CLAUDE.md` first; its
rules (verified models only, `config()` not hand-written config, no raw XML) apply here too.

## 1. Find out what the lab is for

Ask only for what the request doesn't already say, in one message:
- the topic (VLANs, OSPF, ACLs, NAT, ...) and the level of the class;
- roughly how many routers, switches and hosts;
- whether students start from a blank network, a cabled one, or a broken one (a fault to find);
- what the student hands back (a saved .pkt, a screenshot of a ping, answers).

## 2. Write a script, never XML

One Python script per lab, built on the closest example in `references/patterns.md`.
- Models from `pktlib.models()` only. Let `connect()` pick cables.
- Addresses and names in one table at the top of the script, so the answer key and the
  config come from the same place.
- Build the **working** network first, the one the answer key describes.

## 3. Run it and audit it

```bash
uv run python lab.py
uv run pktlib audit lab.pkt
```

The audit includes `refused()` (config Packet Tracer silently drops on load). Fix the script
and run both again until the audit says "nothing found". Don't hand anything over before that.

## 4. Then make the student version

Use `pktlib.lab.Lab` (pattern: `examples/labs/fault_lab.py`). Build the working network on
`lab.net`, then:
- `lab.check(name, fn)` for each thing the finished lab must do;
- `lab.fault(name, brk=..., fixed=..., find=..., audit_says=...)` for each thing broken in the
  student file. A fault is a "should fail": its `fixed` check must fail in the student file.
- `lab.build("lab")` writes nothing unless every check passes on the solution,
  every fault really fails in the student file, and the audit reports exactly the faults
  marked `audit_says`. Fix the script until it builds.
- `lab.grade("handed_in.pkt")` runs the same checks on a student's file.
- If the students work in Packet Tracer itself, `lab.build("lab", pka=True,
  pka_tests=[(src, dst), ...])` also writes `lab.pka`, an activity whose Check Results grades
  them on everything the faults changed, plus the key pings.

See `references/faults.md` for which faults the audit gives away.

## 5. Hand over

- `lab.pkt` (the student file) and, if it differs, `lab_solution.pkt`;
- `lab.pka` if asked for: the same lab as a Packet Tracer activity students check themselves;
- `lab.py`, the script that builds both. It contains the answers, so it is for the lecturer;
- `lab_answers.md` (written by `build`): the addressing table (put it in `lab.notes`), each
  fault with the command that finds it, and the checks. Add each device's intended config to
  `lab.notes` if the lab asks students to write config.

Say plainly that the file has been audited but not opened: the lecturer should open it in
Packet Tracer 8.2, check the links come up, and run the ping the lab is built around before
students see it. pktlib only knows what has been seen in Packet Tracer; anything new (a model
or command no example uses) is the likeliest thing to be wrong.

## Converting an old file

`pktlib.load("old.pkt").save("new.pkt")` restamps an older file for 8.2 and keeps its config
(tried on 6.2 files; anything older or a 7.x is untested, so open the result and check). pktlib refuses to add devices to a pre-8 file; open it in Packet Tracer 8.2 and save
it once first. A file from a newer Packet Tracer than 8.2 is refused.
