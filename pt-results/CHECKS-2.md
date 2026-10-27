# Packet Tracer checks, round 2

Done on Windows, Packet Tracer 8.2.0.0162, 27 Oct 2026, by Claude through computer use, on branch
pt-results-2 from f645345 (pktlib 0.2.1). No pktlib code changed this round: evidence only.
Every file saved from Packet Tracer had its RECENT_FILES emptied before commit (see Setup notes).

## Summary

Passed:
- 1a routed.pkt, 1b wic2t.pkt, 1c eigrp.py: open, links up, RIP v2 and EIGRP converge, DCE clock rate right.
- 2a sample.pka and rich.pka: same items and results as round 1. 2b PyPI 0.2.1 fault_lab.pka: "You completed the activity".
- 3a rich2: DHCP leases, PAT, both ACLs and the static NAT all work in PT. 3b/3c: rich2.pka grades as a student, 0% to 100% one item at a time, then "You completed the activity" with the connectivity test Correct.
- 4: an activity password guards the Activity Wizard only; it's stored as a 32-hex-digit PASS attribute, not plain text.

Failed or needs work in pktlib:
- `scripts/make_templates.py` deleted `src/pktlib/data/activity.xml.gz` (72 tests failed until it was restored). It should leave that file alone or call `make_activity_template.py` (1b).
- New router template carries `clock rate 2000000` on every serial port, the DTE end included (1c, harmless in PT).
- pktlib 0.2.1 reads rich2.pka's 11 items but can't score any of them (score() returns None for DHCP, ACL, NAT and access-group items) and reports `initial` as '' for all (3b).
- Notes: Packet Tracer renders note text as HTML, so `<`, `>` and `<b>` in `net.note()` text get eaten or styled. Passing entities (`&lt;`) works; pktlib could escape for the caller (6).
- pktlib has no fibre cable type; PT refuses fibre on a 2960 copper port anyway (6).

Packet Tracer limits found:
- The wizard can't grade static routes: `Routes > Static Routes` shows no children and ticking it makes no item (3b).
- PAT `overload`, and whether the access-list a NAT rule or access-group names exists, are not graded (3c).
- File > Recent can't be cleared in 8.2, so every save leaks local paths (Setup notes).

Not checked:
- 5 PT 9.x: only 8.2.0 is installed; waiting on Hyper-V and a restart.
- 6 a .pkt of Conor's from another PC: there isn't one on this machine.

New files: `scripts/sources/rich2.py`, `tests/fixtures/rich2-answer.pkt`, `rich2-start.pkt`, `rich2.pka`,
`locked-a.pka` (password alpha1), `locked-b.pka` (password bravo2). Tests: 1429 passed.

## Setup notes
- Fresh clone at C:\Users\Conor\Documents\pktlib-r2 (the old clone kept: it holds a stash and a backup branch only on Windows). Branch pt-results-2 from f645345 (pktlib 0.2.1). Python 3.14.7 venv, pip install -e . plus pytest/hypothesis/xdist/randomly/cov. No uv, no Taskwarrior on this machine.
- Baseline: 1429 passed.
- File > Recent can't be cleared in Packet Tracer 8.2.0: the File > Recent Files submenu only lists files, Options > Preferences (all tabs) has no clear option, and the list lives in an encrypted PT.conf (not the .pkt codec: pktlib.decode gives TagMismatch). PT wrote the list, student ID included, into routed.pkt on save. So every file saved from PT this round was then scrubbed with a script that only empties <RECENT_FILES> (decode, regex, encode) and leaves the rest as PT wrote it.

## 1a routed.pkt
- Opened in PT 8.2: every link up (R1-R2 and R2-R3 serial, both LANs, R2-R4, R4-PC4).
- PC1 `ping 10.3.0.10` (PC3): 3 of 4 replies (first lost to ARP), TTL 125. `ping 10.4.0.10` (PC4): 3 of 4, TTL 125. RIP v2 works.
- Saved from PT over tests/fixtures/routed.pkt (Ctrl+S), RECENT_FILES scrubbed (it held three paths, one an assignment file named with the student ID). Tests: 1429 passed.

## 1b wic2t.pkt
- Made in PT 8.2 from a blank workspace: one 1841 off the palette (named Router0 by PT, kept), opened, power switch off, WIC-2T dragged from the module list into the right-hand slot (labelled SLOT 0), power on. Config tab lists FastEthernet0/0, 0/1, Serial0/0/0, Serial0/0/1. Saved over scripts/sources/wic2t.pkt, RECENT_FILES scrubbed. pktlib reads it as Router0, 1841, modules ['WIC-2T'], ports Fa0/0, Fa0/1, Se0/0/0, Se0/0/1.
- `python scripts/make_templates.py` rewrote base, modules and router-1841-wic2t, and DELETED src/pktlib/data/activity.xml.gz (made by scripts/make_activity_template.py, not by this script). With it gone 72 tests failed (every .pka test and fault_lab). Restored from git for this round (no code changes asked for): make_templates.py should leave activity.xml.gz alone, or call make_activity_template.py.
- Template changes: base.xml.gz 167 changed lines (mostly <VALUE>, UUIDs, timestamps, serials); router-1841-wic2t.xml.gz gained a full STARTUPCONFIG (+85 <LINE>) and a VLAN database the cut-down one lacked; modules.xml.gz only MACs.
- Golden: all 62 test_output_unchanged cases failed (every output's bytes change through the base template); re-recorded with PKTLIB_UPDATE_GOLDEN=1 -n0, 85 hashes changed in tests/golden.json. Then 1429 passed.

## 1c examples/ccna/eigrp.py with the new templates
- Built from the clone; opens in PT 8.2, every link up incl. the R1-R3 serial.
- R1 `show ip eigrp neighbors`: 10.0.12.2 on Fa0/1 and 10.0.13.2 on Se0/0/0 (uptime 00:02:20 / 00:02:13). PASS.
- R1 `show controllers serial0/0/0`: "DCE V.35, clock rate 64000". PASS.
- In the file every other serial port (R1 Se0/0/1, R3 Se0/0/0 and 0/0/1, the DTE end included) carries `clock rate 2000000`: the new router template's own default, so the old "add_module writes clock rate on the DTE end too" TODO now also comes from the template. Harmless in PT.

## 2a sample.pka and rich.pka (PT 8.2)
- sample.pka: opens, instructions show ("Give R1 G0/0 the address 10.0.0.1/24 and PC1 ..."), Check Results works: the same 5 items as round 1 (PC1 Default Gateway, FastEthernet0 IP Address and Subnet Mask, R1 Host Name, Gi0/0 IP Address), all Incorrect at the start. PASS.
- rich.pka: opens, instructions show; Check Results lists the same 11 items as round 1 (3 config lines, OSPF Route0-2 and Router ID, SW1 Fa0/1 Access VLAN and Port Mode, VLAN 10 and 20 names) and both connectivity tests. At the start: everything Incorrect except Port Mode (Correct, as in round 1: unset reads 1); tests PC1>SERVER (Successful) Incorrect, PC2>SERVER (Fail) Correct. PASS.
- Correction to round 1: Check Results labels config-line items "Item" even in this wizard-made file, so the label isn't caused by pktlib's line numbers; it's how Packet Tracer shows them.

## 2b PyPI 0.2.1, fault_lab.pka as a student
- Fresh venv (C:\Users\Conor\Documents\pypi-check, Python 3.14.7), `pip install pktlib==0.2.1` from PyPI; imported from site-packages, version 0.2.1.
- Ran the clone's examples/labs/fault_lab.py with it (already pka=True): wrote fault_lab.pkt, _solution.pkt, _answers.md and .pka. Items: SW1 Fa0/3 Access VLAN (10, start 20), Tech1 Default Gateway (192.168.20.1, start .254); tests Sales2>Sales1 and Tech1>Sales1.
- In PT 8.2: fixed Fa0/3 on SW1's CLI (`switchport access vlan 10`) and Tech1's gateway in IP Configuration, Check Results: "Congratulations Guest! You completed the activity", both connectivity tests Correct. PASS.

## 3a rich2 (scripts/sources/rich2.py)
- R1 2911 edge router: DHCP pool LAN (network, default-router, dns-server 8.8.8.8, excluded .1-.20), default route + static route 10.20.0.0/16 via ISP, standard ACL 20 out on Gi0/0 (deny host 9.9.9.9), extended ACL 110 in on Gi0/0 (deny icmp LAN to 8.8.4.4), PAT overload on Gi0/1 with access-list 1, static NAT SERVER 192.168.1.10 = 203.0.113.10. ISP 2911 with loopbacks 8.8.8.8 / 8.8.4.4 / 9.9.9.9 and a route for 203.0.113.0/24. SW1 2960, PC1 + PC2 on DHCP, SERVER static. Start = same devices, cables and ISP, R1 blank. pktlib audit: answer clean; start reports R1's two shut ports and SERVER's gateway nobody owns (expected: R1 is blank).
- In PT 8.2 (answer): all links up. PC1 leased 192.168.1.22, PC2 192.168.1.21 (gateway .1, the excluded range respected). PC1 `ping 8.8.8.8` 3/4 (first lost to ARP), PC2 4/4: PAT works. PC1 `ping 8.8.4.4`: "Destination host unreachable" from 192.168.1.1 x4 (ACL 110 in). PC1 `ping 9.9.9.9`: timed out (ACL 20 out drops the replies). ISP `ping 203.0.113.10`: 4/5 (static NAT to SERVER). PASS.
- Saved from PT (Ctrl+S) as rich2-answer.pkt and rich2-start.pkt, RECENT_FILES scrubbed, copied to tests/fixtures/. Both load in pktlib with all 6 devices; no paths or student ID left in them.

## 3b Activity Wizard tree for R1 (PT 8.2)
Method: wizard on the answer network, ticked all of R1, saved a scratch .pka, read COMPARISONS from the XML (the file stores the whole tree, ticked or not: 1.8 MB of COMPARISONS for this network).
- DHCP: `R1 > DHCP Server > DHCP Enable` (1); `R1 > DHCP Server > Pools > Pool LAN` (ID = pool name) with children Pool IPs (one value: "LAN\n192.168.1.0\n192.168.1.1\n255.255.255.0\n192.168.1.0\n192.168.1.255\n8.8.8.8\n0.0.0.0\n256"), Name, DNS server IP, Default Gateway, Start IP address, Network Address, Subnet mask, Max User, TFTP Server, WLC Address, Domain Name. `R1 > DHCP Server > Excluded Addresses > 192.168.1.1 192.168.1.20` (ID and value = "first last"). A full duplicate tree sits beside it as `(deprecated) DHCP Server` (no Network Address node). Also `R1 > DHCP Relay Agent > Enabled`.
- Routes: `R1 > Routes > Static Routes > Route0` = "0.0.0.0-0-198.51.100.1-0-1" with ID "Route1", Route1 = "10.20.0.0-16-198.51.100.1-0-1" with ID "Route2" (ID is position, 1-based; label 0-based). Beside each, a `(deprecated) RouteN` whose ID is the value itself. And `R1 > Routes > (deprecated) Static Routes > (deprecated) Route0/1` = "0.0.0.0-0-198.51.100.1-0" (no trailing field). Format: network-prefixlen-nexthop-AD?-?.
- ACLs: `R1 > ACL > 1`, `> 20`, `> 110`: ID = the number, value = every line of that list joined by newline, e.g. 110 = "deny icmp 192.168.1.0 0.0.0.255 host 8.8.4.4\npermit ip any any". Applying: `R1 > Ports > GigabitEthernet0/0 > Access-group In` = "110", `Access-group Out` = "20". Also `ACLV6`, and per-line `Access Control In/Out` under Console/AUX/VTY lines.
- NAT: `R1 > Ports > GigabitEthernet0/0 > NAT Mode` = 1 (inside), Gi0/1 = 2 (outside), unused ports 0. `R1 > NAT > Inside Source List > NAT Source Setting 1` = "GigabitEthernet0/1" (ID "1"). `R1 > NAT > Inside Source Static > NAT Source Setting 1` = "192.168.1.10 203.0.113.10 " (ID = the value, trailing space). `R1 > NAT > Pools`, `Outside Source List`, `Outside Source Static` (empty here).
- Only under running-config lines (`R1 > IOS Configuration > Running Configuration > LINES > NNN ...`): the `overload` keyword and which access-list feeds the PAT rule (the Inside Source List node shows only the interface; its ID "1" may be the list number or an index, not told apart here); the dns-server/default-router as config text; each ACL line on its own (the ACL node is the whole list). Config-line IDs are context-prefixed, e.g. "interface GigabitEthernet0/0 ip access-group 110 in", "ip dhcp pool LAN dns-server 8.8.8.8".
- rich2.pka made in the same wizard session: unticked R1, ticked ACL 110 and 20; DHCP Server > Excluded Addresses (whole node), Pool LAN > Default Gateway, DNS server IP, Network Address; NAT > Inside Source List and Inside Source Static (whole nodes); Ports > Gi0/0 > Access-group In, Access-group Out, NAT Mode; Routes > Static Routes. Connectivity test: Simple PDU PC1 to ISP in the answer network, Test Condition Successful (the first PDU I made said Failed: the wizard restarts the clock and PC1 had no lease yet; deleted it and made it again after PC1 leased). Instructions one paragraph. Initial network: Import File to Initial Network, rich2-start.pkt. Saved as tests/fixtures/rich2.pka, RECENT_FILES scrubbed (4 lists). 249 KB.
- The wizard shows `Routes > Static Routes` with no children, so the only way to tick routes is the head node. That ticks the head node only (checkType 2, no POINTS) with Route0/Route1 left at 0, and Check Results lists "Routes" with 0 points and no items. Result: static routes can't be graded from the wizard's tree in 8.2 (only via running-config lines). Items: 11, not 12.
- pktlib (0.2.1 code) reads rich2.pka: the 11 items with the right paths and expected values, the PC1>ISP test, the instructions. Its `initial` is '' for every item, and `score()` returns None for all 11 on both the answer and start networks (it doesn't know these kinds yet; expected for this round).

## 3c rich2.pka as a student (PT 8.2)
Opened tests/fixtures/rich2.pka (a copy), instructions show, Completion 0%, Check Results: Score 0/11 (Acl 0/4, Ip 0/4, Nat 0/3), connectivity 0/1. Then on R1's CLI, one piece at a time, Completion after each:
1. `ip dhcp excluded-address 192.168.1.1 192.168.1.20`: 9% (Excluded Addresses Correct).
2. `ip dhcp pool LAN` + `network 192.168.1.0 255.255.255.0`: 18% (Network Address).
3. `default-router 192.168.1.1`: 27%.
4. `dns-server 8.8.8.8`: 36%. Every DHCP item turns Correct on its own.
5. Gi0/0 `ip access-group 110 in`, ACL 110 not yet defined, no IP address: 45% (Access-group In Correct regardless).
6. ACL 110 with its two lines in the wrong order (permit first): still 45%. `no access-list 110` and the lines in the right order: 54%. Line order is part of the item.
7. ACL 20 typed in named mode, `ip access-list standard 20` / `deny host 9.9.9.9` / `permit any`: 63%. Counts the same as `access-list 20 ...`.
8. Gi0/0 `ip access-group 20 out`: 72%.
9. Gi0/0 `ip nat inside` (interface still has no address and is shut): 81% (NAT Mode).
10. `ip nat inside source static 192.168.1.10 203.0.113.10`: 90%.
11. `ip nat inside source list 2 interface Gi0/1 overload` (wrong list, list 2 doesn't exist): still 90%. Replaced by `ip nat inside source list 1 interface Gi0/1` WITHOUT overload, access-list 1 not defined: 100%. So the Inside Source List item's ID is the access-list number and its value the interface; `overload` is not checked, nor whether the list exists.
- At 100% items Check Results said "There are connectivity tests that failed" (no interface addresses yet). Then added both interface addresses + no shutdown, Gi0/1 `ip nat outside`, `access-list 1`, the overload form and both routes, fast-forwarded: "Congratulations Guest! You completed the activity", PC1 > ISP:198.51.100.1 Correct.
- Never turn Correct: nothing that was ticked. Not gradable from the tree: static routes (above), `overload`, `ip nat outside` on Gi0/1 (not ticked here; it's Gi0/1 > NAT Mode 2), and whether the ACL a rule names exists.

## 3d one-liners
- ACL by number vs by name: the ACL node's ID is the list's name or number ("20"), and named-mode entry of a numbered list (`ip access-list standard 20`) scores the same as `access-list 20`; a list with a different name would be a different node.
- ACL line order: yes, part of the item. The value is every line joined by newlines, and the same lines in another order stay Incorrect.
- NAT pool: a separate node, `R1 > NAT > Pools`, beside Inside Source List / Inside Source Static (empty in rich2, so its children's format wasn't seen).
- DHCP excluded-address: its own item, `R1 > DHCP Server > Excluded Addresses > <first> <last>`, separate from the pool, and it turned Correct with no pool configured.

## 4 Activity passwords (PT 8.2)
- Made from tests/fixtures/sample-answer.pkt: Activity Wizard, current network as answer, ticked R1 > Host Name, Password page: "alpha1" twice, Enable Password, Save As locked-a.pka. Then in the same wizard session "bravo2", Enable Password, Save As locked-b.pka. No initial network set (so the student workspace is blank). Throwaway test passwords: locked-a = alpha1, locked-b = bravo2. Both saved to tests/fixtures/, RECENT_FILES scrubbed.
- Where the password lives: the `<ACTIVITY ...>` element's PASS attribute: locked-a PASS="109595E666F050DDCDA9F96F3E6ADA9E", locked-b PASS="35CBCF0834984A49B93FE3462ED1212F"; sample.pka (no password) has PASS="". It's 32 hex digits, not the plain text and not a plain MD5 of it (UTF-8, UTF-16LE and UTF-16BE all tried). The two files differ only in PASS (and the RECENT_FILES paths). ENABLED="no" in all three, so ENABLED isn't the password switch. The `<PASS/>` under options and `<MU_PASSWORD>cisco</MU_PASSWORD>` (multiuser default) are unrelated.
- pktlib 0.2.1 reads both (one item R1 Host Name = R1) and decode/encode round-trips them byte for byte.
- locked.pka (a copy of locked-a) reopened as a student: instructions window and Check Results work as normal. Extensions > Activity Wizard (and Ctrl+W) asks "Please enter the password"; "wrong" gives "The password you entered is incorrect!" and nothing opens. Every other menu stays enabled: File > Save / Save As / Save As PKZ, Extensions (Multiuser, IPC, Scripting...), so the password guards only the wizard. With "alpha1" the wizard opens, and the workspace behind it now shows the ANSWER network; exiting asks to save, then "Exiting the Activity Wizard will give you a new workspace". So the password does protect the answers, but only as well as that hash.

## 5 PT 9.x
Not checked: only 8.2.0 is installed on this PC. Conor is installing Hyper-V for the newest Packet Tracer; it needs a restart, so this waits for a later round.

## 6 Quick 8.2 quirks
- Note with `<` and `>`: pktlib wrote `net.note('pktlib note: if x < 10 and y > 3 then <b>not bold</b> & "quoted"')`, XML-escaped once (`&lt;`, `&gt;`, `&amp;`). Packet Tracer shows it as HTML: "pktlib note: if x 3 then **not bold** & "quoted"" (`< 10 and y >` swallowed as a tag, `<b>` made bold). A note typed in the PT GUI, "gui note: a < b > c <i>x</i> & d", shows the same way ("a c *x* & d") and is stored the same way (`&lt;` and a bare `>`), so this is how PT treats note text, not a pktlib bug. pktlib reads both notes back with their full text and keeps them through load/save. Workaround that works: pass HTML entities, `net.note('x &lt; 10 ... &lt;b&gt;not bold&lt;/b&gt; &amp; done')` displays literally in PT ("x < 10 and y > 3, <b>not bold</b> & done"). pktlib could do that escaping itself.
- Network description dialog (toolbar "Network Information", the (i)): typed "desc: lab for <ACL> tests & more"; on reopening the dialog it reads "desc: lab for  tests & more" (the dialog itself dropped `<ACL>`). Stored in `<NETWORK>`'s own `<DESCRIPTION>` (the one after the devices, not the many empty per-device ones) as a whole Qt rich-text HTML document, XML-escaped, with `&` stored as `&amp;amp;`. pktlib has no API for it but keeps it through load/save (only `>` re-escaped as `&gt;`, same XML). The scenario's own `<DESCRIPTION translate="true"/>` is separate.
- Fibre to a 2960 copper port: Connections > Fiber, click SW1 (2960-24TT): the port menu lists every port (Fa0/1-24 and Gi0/2; Gi0/1 already used), nothing greyed out; picking FastEthernet0/1 gives "Connection Error: The cable cannot be connected to that port." and no cable. pktlib can't ask for fibre at all (its Cable type is straight, cross, serial, coax, phone).
- A .pkt of Conor's from another PC: not checked. None on this machine: the only .pkt files outside the repos are the CA1 submission in Downloads (byte for byte the college copy, saved on this PC) and a lecturer start file (course file, not touched). Needs a file from the Mac or the work machine.
