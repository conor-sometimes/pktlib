# Packet Tracer checks, round 3

Done on Windows, Packet Tracer 8.2.0.0162, 24 Nov 2026, by Claude through computer use, on branch
pt-results-3 from 3cae178 (PR #12). Files built with `scripts/pt_checks.py 3`.

Setup note: in a PT CLI, text typed through the clipboard paste path is dropped, so commands were
typed short (IOS abbreviations) one line at a time.

## 1. vtp password (#8)

- `show vtp password` on opening: `VTP Password: two`. `show vtp status`: VTP Domain Name `LAB`,
  mode Server, Configuration Revision 0.
- `show running-config | include vtp`: no output. PT does not show `vtp` lines in the running config.
- `vtp password three` answers `Setting device VLAN database password to three`. After `copy
  running-config startup-config`, `show vtp password` gives `three`; `show startup-config` has no vtp
  line either.
- Saved as vtp-pt.pkt. PT drops every `vtp` line from SW1's RUNNINGCONFIG and STARTUPCONFIG and
  writes the settings into the device's `<VTP>` element instead (twice in the file):
  `<DOMAIN_NAME>LAB</DOMAIN_NAME> <MODE>0</MODE> <VERSION>1</VERSION> <PASSWORD>three</PASSWORD>
  <CONFIG_REVISION>0</CONFIG_REVISION>`. In the pktlib-built file that element is empty and the
  settings ride on config lines (`vtp domain LAB`, `vtp password two`), which PT applies on load.
- So: #8's fix (one line, the last) is right for files pktlib writes. For files PT saved, the VTP
  domain and password live only in `<VTP>`; anything that reads them from config lines sees none.

## 2. Router-on-a-stick answer (#9)

- On opening, R1 logs `%LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet0/1.10,
  changed state to up` (and the same for 0/1 and 0/1.20).
- `show ip interface brief`: `GigabitEthernet0/1.10  10.0.10.1  YES manual up  up` and
  `GigabitEthernet0/1.20  10.0.20.1  YES manual up  up`; G0/1 `unassigned YES unset up up`.
- `show running-config` puts the sub-interface blocks straight after `interface GigabitEthernet0/1`
  and before `interface Vlan1`, as IOS does, although pktlib wrote them after `line vty`. PT
  rebuilds the running config from its own model; the order pktlib writes doesn't reach the CLI.
- The 'PC1 to PC2' PDU: first fire `Failed` (ARP), second fire `Successful`.
- Passed.

## 3. Router-on-a-stick activity (#9)

- Opened as a student: `Completion: 0%`. Check Results: R1 > IOS Configuration > Running
  Configuration > LINES lists **6** items, each named just `Item`, all Incorrect; Score 0/6,
  Connectivity Tests 0/1. The file has 7 ticked items: PT does not list `051  no shutdown`.
- `interface g0/1`, `no shutdown`: still 0/6 (the G0/1 link comes up). IOS never prints `no
  shutdown` in a running config, so that item could never match; PT drops it from the list. diff_items
  should not make an item for `no shutdown` (it costs nothing in PT, but it's a dead item).
- Then one line at a time, Check Results after each: `interface g0/1.10` 1/6 (16%), `encapsulation
  dot1Q 10` 2/6, `ip address 10.0.10.1 255.255.255.0` 3/6, `interface g0/1.20` 4/6, `encapsulation
  dot1Q 20` 5/6, `ip address 10.0.20.1 255.255.255.0`: `Congratulations Guest! You completed the
  activity.`, Score 7/7, items 6/6, connectivity test 1 `Correct  Successful  PC1  PC2 : 10.0.20.10
  ICMP`.
- So the line number in the item (`078 interface GigabitEthernet0/1.10`) does not matter: the
  student's IOS puts the blocks under G0/1 and each item still turned Correct. No need for config()
  to reorder sub-interfaces for grading.
- Activity Wizard > Answer Network: PT rebuilds Running Configuration > LINES from the answer
  network, with its own numbers: `052 interface GigabitEthernet0/1.10`, `053  encapsulation dot1Q
  10`, `054  ip address 10.0.10.1 255.255.255.0` (ticked). Startup Configuration > LINES keeps
  pktlib's order: `078 ...`, `079 ...`, `080 ...` (unticked). R1 > Ports lists
  `GigabitEthernet0/1.10` with leaf `IP Address: 10.0.10.1` (component Ip), and RIP > Passive
  Interface has `GigabitEthernet0/1.10: 0`.
- Passed.

## 4. Access port activity (#10)

- Opened as a student: `Completion: 0%`. Check Results: SW1 > IOS Configuration > Running
  Configuration > LINES, one item named `Item`, Incorrect, Score 0/1.
- `interface fa0/5`, `switchport mode trunk`: Incorrect, 0/1.
- `switchport mode access`: `Congratulations Guest! You completed the activity.`, Correct, 1/1.
- As in check 3, Check Results names a line item only `Item`; the line text shows only in the
  Activity Wizard.
- Passed.

## 5. Spaces in device names (#11)

- New workspace, a 2960 (Switch0) and a PC-PT (PC0) added from the device box.
- Config > Display Name accepts, unchanged: `A.B(C)#D/E&F`, a 70-character name (the window title
  shows all 70), `Switch 7` and `PC 7`. The workspace labels show `Switch 7` and `PC 7`.
- Switch CLI: `hostname Switch 7` is refused with `% Invalid input detected at '^' marker.`, the
  caret under `7`. `hostname Sw.1/#` is accepted (prompt `Sw.1/#(config)#`).
- The display name does not follow the hostname: Config shows Display Name `Switch 7`, Hostname
  `Sw.1/#`.
- Saved as spaced-name.pkt. In the XML the device NAMEs are `Switch 7` and `PC 7`, the running
  config has `hostname Sw.1/#`.
- pktlib (main, 3cae178): there is no `pktlib show` (the TODO's wording); `pktlib info` lists `Switch
  7  Switch 2960-24TT  at 657,252` and `PC 7  Pc PC-PT  at 1053.5,252`; `pktlib audit`: nothing
  found. Loading works and `device.name` is `Switch 7`. Making one is refused: `net.switch("Switch
  8")` raises `PktError bad device name 'Switch 8': letter first, then up to 63 letters, digits, _
  or -`.
- So a display name in PT is free text (spaces, punctuation, 70+ characters); only the IOS hostname
  refuses spaces. pktlib's rule is the hostname's rule applied to the display name. #11 can allow
  spaces in the name, as long as whatever pktlib derives a hostname from the name doesn't pass the
  space on.

## 6. Flash folders (PR #6)

- `dir flash:` lists the `mkdir()` folder on all three:
  - D1 (2901): `4  drw-  0  <no date>  ipsdir`
  - D2 (2960): `5  drw-  0  <no date>  ipsdir`
  - D3 (3650): `4  drw-  0  <no date>  ipsdir`
- Size is **0**, not 192 as the `mkdir()` docstring says. A folder typed in the CLI this round
  (below) also shows 0, so 0 is just what PT shows for an empty folder here.
- On D1, `mkdir flash:ipsdir/inner` answers `Create directory filename [ipsdir/inner]?` then
  `Created dir flash:ipsdir/inner`, but `dir flash:` then lists a top-level `5  drw-  0  <no date>
  ipsdirinner`: PT drops the slash. There are no folders inside folders. `dir flash:ipsdir` gives
  `%Error opening flash0:/flash:ipsdir (File Not Found)`, `dir ipsdir` gives `%Error opening
  flash0:/ipsdir (File Not Found)`, and `cd ipsdir` is `% Invalid input`.
- Saved as folders-pt.pkt: PT keeps pktlib's `<FILE class="CDirectory">` shape for `ipsdir` as
  written, and saves the typed folder the same way with `<NAME>ipsdirinner</NAME>`.
- So `mkdir()` is right to refuse nested folders. Its docstring's "size 192" should say 0.

## 7. Short passwords (PR #6)

The file has `security passwords min-length 10` on both, R1 (2901) with `line con 0` / `password
cisco`, `line aux 0` / `password cisco`, `line vty 0 4` / `login` / `password 7 0822455D0A16`, and
SW1 (2960) with con and `line vty 0 4` both `password cisco`.

| Device | Block | After opening | After `copy run start`, `reload` |
|---|---|---|---|
| R1 | line con 0 | `password cisco` | gone |
| R1 | line aux 0 | `password cisco` | gone |
| R1 | line vty 0 4 | `password 7 0822455D0A16` | gone (`login` stays) |
| SW1 | line con 0 | `password cisco` | `password cisco` |
| SW1 | line vty 0 4 | `password cisco` | `password cisco` |

- R1's `show startup-config` after the reload still has all three passwords: PT drops them when it
  loads startup into running, not when it saves.
- R1 keeps `security passwords min-length 10` after the reload.
- SW1 has no `security passwords min-length` line in its running config at all, before or after:
  on a 2960 `security ?` is `% Unrecognized command`. PT dropped the line on load, so nothing
  enforces a minimum and both passwords survive.
- `pktlib audit` on the file reports one problem, and it's the wrong one: `SW1: password cisco under
  line vty 0 4 is dropped by Packet Tracer 8.2 on a reload`. SW1 keeps it. R1's con, aux and
  `password 7` VTY, all dropped, aren't reported.
- For `short_passwords()`: count console and aux lines and the `password 7` form too (the
  decrypted length, `cisco` here, is what's checked, or the whole line goes regardless); and on a
  2960, `security passwords min-length` should be reported as dropped by `refused()`, with no short
  password warnings.

## 8. Command log

- It shows in the GUI: **Options > View Command Log** (Ctrl+Shift+V) opens an `IOS Command Log`
  window with columns Time, Device, Prompt, Command, Resolved Command, and an Update button. Nothing
  in Extensions, Tools, View or Edit, or in the device windows.
- tests/fixtures/rich2-answer.pkt shows its 11 entries, all on ISP, 27 Oct, e.g. `1  Tue Oct 27
  15:50:36 2026  ISP  ISP>  enable  enable`, `3 ... ISP(config)#  interface fa0/3  interface
  FastEthernet0/3`, `11  Tue Oct 27 15:51:18 2026  ISP  ISP#  ping 203.0.113.10`.
- Typed on R1 `enable`, `sh ip int br`: entries 12 and 13 appear (`R1#  sh ip int br  show ip
  interface brief`). Saved as a scratch copy: COMMAND_LOGS has 11 LOG_ENTRY before, 13 after (then
  deleted). Each LOG_ENTRY is hex of the five fields joined by NULs: `Tue Nov 24 12:15:06 2026`,
  `R1`, `R1#`, `sh ip int br`, `show ip interface brief`.
- In 04-access-port-activity.pka opened as a student (0 entries in the file), `enable` and `sh vlan
  br` on SW1 show in the same window: the log works inside an activity.
- So a lecturer opening a student's file sees every command they typed, when, and on which device.
  A file pktlib builds has an empty log; one that went through Packet Tracer has a history.

## Summary

Passed: 2 and 3 (#9: sub-interfaces come up, ping works, each sub-interface line grades Correct
whatever its line number, 100% at the end), 4 (#10: access port graded, Incorrect with trunk).

Needs work in pktlib:
- #9: diff_items makes an item for `no shutdown` under G0/1. IOS never prints it, PT drops it from
  Check Results (6 of 7 items listed), so it's dead weight. Leave it out.
- #8: right for files pktlib writes, but PT saves VTP domain and password in the device's `<VTP>`
  element and strips the `vtp` lines from both configs. Reading a PT-saved file, pktlib would see
  no VTP settings.
- #11: PT's display name takes spaces, punctuation and 70 characters; only `hostname` refuses a
  space. pktlib can allow spaces in names (not in a hostname derived from one).
- PR #6, mkdir(): docstring says size 192, PT shows 0. Nested folders really don't exist in PT
  (`ipsdir/inner` becomes `ipsdirinner`), so refusing them stays.
- PR #6, short_passwords(): wrong both ways. On a 2901 under min-length 10 a reload drops the con,
  aux and `password 7` VTY passwords, none reported. On a 2960 `security passwords min-length` isn't
  a command (dropped on load), so nothing is dropped, yet SW1's VTY is reported.

Found: Options > View Command Log shows the whole typed history to whoever opens the file.

Not changed: no pktlib code this round, evidence only. Files kept in `tests/fixtures/`
(vtp-pt.pkt, spaced-name.pkt, folders-pt.pkt), each saved by PT with RECENT_FILES then emptied (it
held this PC's paths) and nothing else touched.
