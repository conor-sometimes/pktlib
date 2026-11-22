# pktlib: what's open (22 Nov 2026)

```
uv run pytest                  # everything; must pass before a commit
just examples                  # rebuild and audit the examples into out/
```

## To check in Packet Tracer

### Round 3 (issues #8 to #11, PR #6, 22 Nov)

Packet Tracer 8.2.0 (build 8.2.0.0162). Build the files first: `uv run python
scripts/pt_checks.py 3` writes them to `out/pt-checks-3/` (git ignores it). Work on a branch and
write what Packet Tracer did, word for word where it shows text, in `pt-results/CHECKS-3.md`, as
rounds 1 and 2 did. Empty RECENT_FILES in any `.pkt` saved from Packet Tracer before committing
it. Each answer ends up as a test with the date in it, then the item comes off this list.

1. **vtp password** (`01-vtp-password.pkt`, #8). pktlib now keeps one `vtp password` line, the
   last. Real IOS keeps VTP settings in vlan.dat, so it's not known whether Packet Tracer saves
   the line at all. On SW1: `show vtp password` (expect `two`), `show vtp status`, `show
   running-config | include vtp`. Then `vtp password three`, `end`, `copy running-config
   startup-config`, save as vtp-pt.pkt, and look for `vtp` lines in SW1's running and startup
   config in that file.
2. **Router-on-a-stick answer** (`02-on-a-stick-answer.pkt`, #9). On R1, `show ip interface
   brief` and `show running-config`; click the "PC1 to PC2" PDU. Expect G0/1.10 and G0/1.20
   up/up and the ping to succeed. Note where Packet Tracer shows the sub-interface blocks:
   pktlib writes them after `line vty`, not under G0/1 as IOS saves them.
3. **Router-on-a-stick activity** (`03-on-a-stick-activity.pka`, #9). Open as a student, Check
   Results, then configure R1 one line at a time (`interface g0/1`, `no shutdown`, `interface
   g0/1.10`, `encapsulation dot1Q 10`, `ip address 10.0.10.1 255.255.255.0`, the same for .20),
   checking results after each. Expect 0% to 100%, each item turning Correct as its line goes
   in, and the connectivity test Correct. The risk: each line item carries the answer's line
   number (`078 interface GigabitEthernet0/1.10`), and a student's IOS puts the blocks under
   G0/1. If Check Results matches by position, a right answer fails, and `config()` must place
   sub-interfaces as IOS does. Then open the Activity Wizard > Answer Network and note whether R1
   > Ports lists GigabitEthernet0/1.10, and with what leaves.
4. **Access port activity** (`04-access-port-activity.pka`, #10). Open as a student, Check
   Results; on SW1 `interface fa0/5`, `switchport mode trunk`, Check Results; then `switchport
   mode access`, Check Results. Expect Incorrect, Incorrect, Correct. Note the item's name as
   Check Results shows it.
5. **Spaces in device names** (no file, #11). In Packet Tracer: add a 2960 and a PC-PT, set
   Config > Display Name to `Switch 7` and `PC 7`. Try a name with each of `. ( ) # / &` and a
   70-character name. On the switch CLI, `hostname Switch 7`. Save as spaced-name.pkt, then `uv
   run pktlib show spaced-name.pkt`. Record which names are accepted, what the hostname becomes
   and whether the display name follows it, and what pktlib says. Keep the file for
   tests/fixtures. pktlib refuses spaces until this is seen.
6. **Flash folders** (`06-flash-folders.pkt`, PR #6). `ipsdir` made by `mkdir()` on a 2901 (D1),
   a 2960 (D2) and a 3650 (D3); only a hand-written folder placed first on a 2901 has been seen
   working (6 Nov). `dir flash:` on each: expect `ipsdir` as `drw-`, size 192. On D1 also `mkdir
   flash:ipsdir/inner` and `dir flash:ipsdir` (`mkdir()` refuses nested folders until one is
   seen), and save as folders-pt.pkt.
7. **Short passwords** (`07-short-passwords.pkt`, PR #6). Under min-length 10, only a plain VTY
   password on a 2901 has been seen dropped on reload. This file has short passwords on R1's
   con, aux and VTY (`password 7` form) and SW1's con and VTY; its audit warning on SW1 is
   expected. On both: `show running-config | section line`, `copy running-config
   startup-config`, `reload`, the same `show` again. Record which passwords survive; what's
   dropped goes into `short_passwords()`.
8. **Command log** (no file). Packet Tracer saves every CLI command typed, with time and device,
   in COMMAND_LOGS (11 entries in tests/fixtures/rich2-answer.pkt, from 27 Oct); a file pktlib
   builds has none. Not known: whether the GUI shows it, so whether a lecturer marking a file
   would see it. Open rich2-answer.pkt, look through the menus (Extensions, Tools, View,
   Options) and the device windows for a command log or history. Type a few commands on R1, save
   a scratch copy, and count `COMMAND_LOGS/LOG_ENTRY` before and after (`pktlib.decode`). Do the
   same in a `.pka` from this round opened as a student. Record where the log shows, or that it
   doesn't.

### Older

- `examples/fault_lab.py`: open `fault_lab.pkt`, confirm Sales2 can't reach Sales1 (wrong
  VLAN) and Tech1 can't reach its gateway; then `fault_lab_solution.pkt` pings clean.
- `examples/enterprise.py`: `ipconfig` on STAFF1. Its link-local should be
  FE80::202:BAFF:FE64:6A24, not the template's FE80::290:CFF:FEC7:8E5A. The fix for cloned
  link-locals hasn't been seen in the GUI yet.
- `show ip ips all` on a router with `ip ips config location flash:ipsdir` and a folder made by
  `mkdir()`: the location should be listed.

## Limits checked in Packet Tracer (round 1, 27 Oct)

Done: pktlib refuses, warns or audits each silent drop (VLAN name in use, 2960 port
address, a cable within one device, 7960 config, Bluetooth address, network or broadcast or
overlapping router addresses). Accepted by Packet Tracer, so left alone: 200-character and
spaced VLAN names, renaming VLAN 1, device names differing only in case, control
characters, odd PC addresses (network, broadcast, /32, the gateway's own; the network one
still pinged), a 1000-bit RSA key (SSH works). Coordinates clamp to about x 100-3900, y from 100. Still open:

- Is it `include-connected` Packet Tracer drops under `ipv6 router eigrp`, or any
  `redistribute ospf` there? stress/routing/rt05 now writes it without; check V6-B still has
  D routes and the far side EX routes.

## Config: a block entered twice

- Since 27 Oct a command entered twice in a flat block (interface, router ospf, line) is kept
  once, as IOS shows it. That dropped one duplicate line each from stress/routing/rt02 (STB1's
  second `network 10.11.8.0 0.0.0.255 area 1`) and rt05 (V6-B's second `no auto-summary`).
  Re-open both in Packet Tracer to confirm the routes still come up.

- A block header outside `_MERGEABLE` entered a second time (`ipv6 router ospf 1`, then later
  `ipv6 router ospf 1` again) gets a second copy before `end`; IOS would merge it into the first.
  stress/routing/rt05 relies on the second-copy form and was checked in Packet Tracer that way
  (OSPFv3 routes learned). Merging is one line in `merge_config` (found by the idempotence
  property in tests/test_properties.py, 27 Oct); do it once rt05 rebuilt with merging has been
  opened in Packet Tracer and its routes still come up.

## Bugs and rough edges

- `add_module` writes `clock rate` on every new serial port, the DTE end too (harmless, untidy).
- Interface blocks for added modules land after `line vty`; Packet Tracer's own saves keep IOS
  order. Works today; check nothing else is order-sensitive the way Port-channel was.
- Grow `refused()` as more silent refusals turn up. Only add what Packet Tracer was seen
  rejecting.
- End devices are IPv4 only (`set_ip` raises for IPv6).

## Ideas, not started

- `scripts/hover_rig.py`: one file with every model, to read port names off the hover table
  when a new edition lands.
- Physical view (wiring closets, buildings, wireless range). Not until a lab needs it.

## Before publishing

- No coursework in the repo or the package: every sample is listed with its origin in
  `tests/fixtures/README.md`, and a test fails on one that isn't.
