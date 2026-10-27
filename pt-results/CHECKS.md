# Packet Tracer checks

Done on Windows, Packet Tracer 8.2.0.0162, 27 Oct 2026, by Claude through computer use. 'Re-save' means the file was opened and saved again by Packet Tracer (the `_pt.pkt` copies), then compared with pktlib.
Packet Tracer 8.2.0 (build 8.2.0.0162). For each: open the file (or do the steps), do what it
says, and fill in **Result** with what Packet Tracer did, word for word where it shows text.
Note anything unexpected even if it isn't asked about. Screenshots welcome.

## What needs doing (summary)

Fixed already on this branch (commit da169e2): the 2620XM/2621XM onboard WIC serials are Serial0/0
to 0/3. pktlib wrote Serial0/0/0 and Packet Tracer refused the whole file (check 17; stress rt01,
rt02, rt03 scripts and golden hashes updated, test pinned).

Bugs found, fixed on this branch afterwards (27 Oct, each re-checked in Packet Tracer):
- Hub-PT ports are named by slot (a hub with slot 2 empty shows FastEthernet0, 1, 3, 4, 5), but
  pktlib reads Packet Tracer's own file as FastEthernet0 to 4 (check 24; fixture
  tests/fixtures/hub-card-removed.pkt).
- examples/ccna/ipv6.py gives R3 g0/2 10.0.23.3/30, the broadcast address; Packet Tracer drops it and
  2 of the 3 ping scenarios fail (check 25). The audit should flag network and broadcast addresses
  on router interfaces (Packet Tracer refuses both: checks 6 and 25).
- examples/labs/fault_lab.py: the 'Tech1 to its gateway' ping can't show the wrong-gateway fault,
  because it stays on Tech1's subnet (check 26).
- IPv6: Packet Tracer drops `default-information originate always` under `ipv6 router ospf 1` and
  `redistribute ospf 1 metric ... include-connected` under `ipv6 router eigrp 200` (checks 18 and 19).

Things pktlib should refuse (Packet Tracer drops them silently): a second VLAN with a name already
in use (3); an address on a 2960 port, and `no switchport` there (7); a cable between two ports of
one device (8); config() on a 7960 phone (11); set_ip on a laptop's Bluetooth port (14); a network
address, or an overlapping subnet, on a router interface (6).

Confirmed, so pktlib can go ahead: drop `exit` (12); DHCP wins over a static address (13); merge a
repeated `ipv6 router ospf` block (19); Port-channels in number order (20); write username,
ip ssh and ip domain-name where IOS saves them (21, 22: both orders work, PT re-saves both the same);
coordinates clamp to about x 100-3900, y from 100 (15); control characters survive (16).

New samples in tests/fixtures/: pc-ipv6.pkt (23), hub-card-removed.pkt (24), sample.pka and
sample-answer.pkt (28).

## 1. every-model (`out/pt-checks/01-every-model.pkt`)

- **Why:** pktlib adds all 64 palette models from templates; they should load as Packet Tracer's own.
- **Do:** Open. Click through a few of each kind (router, switch, end device, wireless, home kit).
- **Expect:** Opens with no error; every device is powered as it would be off the palette.
- **Result:**
  - every-model: opened with no error (only the Network Controller external-access prompt, declined). PT copy saved.
  - (re-save): all 64 devices survive PT's re-save, none missing, no power state changed.

## 2. module-while-powered (`out/pt-checks/02-module-while-powered.pkt`)

- **Why:** pktlib fits cards into a powered-on device (the GUI makes you switch it off first).
- **Do:** Open. On R1 and R2, `show ip interface brief`. Click the 'Serial link' PDU in the scenario.
- **Expect:** Serial0/0/0 up/up on both; the ping succeeds. If a card isn't recognised, say which.
- **Result:**
  - module-while-powered: links green both ends on open; 'Serial link' PDU Successful.

## 3. vlan-names (`out/pt-checks/03-vlan-names.pkt`)

- **Why:** VLAN name limits pktlib doesn't enforce yet (it takes 200 characters).
- **Do:** Open. On SW1, `show vlan brief`.
- **Expect:** Record which names show and how: 32 chars, 33 chars, 200 chars, spaces, two VLANs named SAME, VLAN 1 renamed. Any truncation or refusal is a rule pktlib should copy.
- **Result:**
  - vlan-names: opened fine, PT copy saved.
  - vlan-names (from PT's re-save): every name kept exactly as written: 32 A's, 33 B's, the 200-character C name, 'HAS SPACES', VLAN 1 renamed 'RENAMED-DEFAULT'. No truncation. The one refusal: VLAN 60 'SAME' is GONE; VLAN 50 'SAME' stays. So PT refuses a second VLAN with a name already in use (and drops the whole VLAN), but has no length limit at 200.

## 4. names-by-case (`out/pt-checks/04-names-by-case.pkt`)

- **Why:** pktlib allows R1 and r1 at once, and 64-character names.
- **Do:** Open. Look at the device names on the workspace; try renaming r1 to R1 in the GUI.
- **Expect:** Record whether both load and whether Packet Tracer treats names case-insensitively.
- **Result:**
  - names-by-case: both R1 and r1 load, the 64-char name loads and shows in full. Renaming r1 to R1 in Config > Display Name: the field turns red at 'R1' and is not applied (it kept 'R' from the first keystroke), so PT treats device names case-insensitively and refuses a clash in the GUI. A file with both loads fine.

## 5. odd-pc-addresses (`out/pt-checks/05-odd-pc-addresses.pkt`)

- **Why:** PC addresses pktlib accepts but IOS-style checks might not: network address, broadcast, /32, the gateway's own address.
- **Do:** Open. Look at each ODD PC's IP Configuration; click the 'Odd addresses' PDU.
- **Expect:** Record which addresses Packet Tracer keeps, changes or flags.
- **Result:**
  - odd-pc-addresses: 'Odd addresses' PDU (ODD0 to R1) Successful. Addresses kept: see diff.
  - odd-pc-addresses (re-save): PT keeps every address unchanged: ODD0 10.0.0.0/24, ODD1 10.0.0.255/24, ODD2 10.0.0.20/32 (no gateway), ODD3 10.0.0.1/24 (the gateway's own address). ODD0 (network address) still pinged R1 Successfully.

## 6. router-odd-addresses (`out/pt-checks/06-router-odd-addresses.pkt`)

- **Why:** A network address on an interface, and two interfaces in one subnet.
- **Do:** Open. On R1, `show ip interface brief` and `show running-config`.
- **Expect:** Record whether g0/0 kept 10.0.0.0/24 and whether g0/2 was refused for overlapping g0/1.
- **Result:**
  - router-odd-addresses (re-save): g0/0 `ip address 10.0.0.0 255.255.255.0` REFUSED (became `no ip address`). g0/1 10.0.0.129/25 kept. g0/2 10.0.0.130/25 REFUSED for overlapping g0/1 (became `no ip address`). The `no shutdown`s took (no shutdown line left).

## 7. l2-port-address (`out/pt-checks/07-l2-port-address.pkt`)

- **Why:** `no switchport` and an address on a 2960 port, which has no routed ports on real IOS.
- **Do:** Open. On SW1, `show running-config interface fa0/1`.
- **Expect:** Record what's left of the two lines.
- **Result:**
  - l2-port-address (re-save): both `no switchport` and `ip address 10.0.0.1 255.255.255.0` on the 2960's Fa0/1 are dropped; nothing left of them.

## 8. same-switch-loop (`out/pt-checks/08-same-switch-loop.pkt`)

- **Why:** A cable from one switch port to another on the same switch.
- **Do:** Open.
- **Expect:** Record whether the file loads and whether the link comes up.
- **Result:**
  - same-switch-loop: file loads. No cable is drawn on the workspace and no link lights show on SW1 (see the PT copy for whether the link survived).
  - (re-save): PT DROPS the cable: the SW1 Fa0/1 to Fa0/2 link is gone from the re-saved file. File still loads. pktlib should refuse a cable between two ports of one device.

## 9. rsa-1000 (`out/pt-checks/09-rsa-1000.pkt`)

- **Why:** An RSA modulus that isn't a power of 2.
- **Do:** Open. On R1, `show crypto key mypubkey rsa`; from PC1, `ssh -l admin 10.0.0.1` (password cisco).
- **Expect:** Record the modulus shown and whether SSH works.
- **Result:**
  - rsa-1000: SSH from PC1 (ssh -l admin 10.0.0.1, password cisco) logs in to R1>. 'show crypto key mypubkey rsa' over that session shows 'Key name: R1.lab.local', General Purpose Key, not exportable, generated 0:0:30 UTC March 1 1993, the key data rows, and the temporary key R1.lab.local.server. It does NOT print a modulus size, so the 1000 isn't visible there; the key is accepted and SSH works.

## 10. pdu-edge-cases (`out/pt-checks/10-pdu-edge-cases.pkt`)

- **Why:** A Simple PDU from a 2960 with no SVI.
- **Do:** Open. Click both PDUs in the scenario list.
- **Expect:** Record what each shows (Successful, Failed, or refused when the file loads).
- **Result:**
  - pdu-edge-cases: one scenario 'From a switch with no SVI' with one PDU (SW1 to PC1) shows on load; fired twice: Failed. Second PDU: see diff.
  - (cont.): second scenario 'Plain' (PC1 to R1 10.0.0.1): Successful. So the switch-with-no-SVI PDU loads and fires, and Fails; nothing was refused on load.

## 11. phone-config (`out/pt-checks/11-phone-config.pkt`)

- **Why:** config() on a 7960 phone (pktlib lets it through; has_ios is true for the phone).
- **Do:** Open. Look at the phone's config tab or CLI if it has one.
- **Expect:** Record whether the hostname line did anything.
- **Result:**
  - phone-config: the 7960 has tabs Physical, Config, GUI, Attributes; no CLI. Config shows only Display Name 'PH1'. The hostname line did nothing visible; the name stays PH1. (PT copy saved: see diff for whether the config text survives.)
  - (re-save): PT drops the phone's config entirely: `hostname SHOULD-THIS-STICK` is gone from the re-saved file (running config empty). config() on a 7960 does nothing; pktlib should refuse it.

## 12. mode-lines (`out/pt-checks/12-mode-lines.pkt`)

- **Why:** `exit` written inside an interface block, then an address: pktlib now leaves exit out.
- **Do:** Open. On R1, `show running-config interface g0/1`.
- **Expect:** If the address is NOT on g0/1, Packet Tracer replays exit as IOS does, and pktlib was right to drop it.
- **Result:**
  - mode-lines (re-save): g0/1 keeps `description before-exit` but NOT 10.9.9.1, so PT replays `exit` like IOS and the later lines leave the interface: pktlib was right to drop `exit`. Also the `shutdown` written after the exit didn't land on g0/1 (g0/1 comes up with no shutdown line).

## 13. dhcp-and-static (`out/pt-checks/13-dhcp-and-static.pkt`)

- **Why:** A PC with DHCP on and a static address at once.
- **Do:** Open. Look at PC1's IP Configuration; `ipconfig` on its desktop.
- **Expect:** Record which one wins.
- **Result:**
  - dhcp-and-static: DHCP wins. PC1's IP Configuration shows DHCP selected with 10.0.0.2 / 255.255.255.0, gateway 10.0.0.1 (a lease from R1's pool), not the static 10.0.0.10.

## 14. bluetooth-address (`out/pt-checks/14-bluetooth-address.pkt`)

- **Why:** set_ip on a laptop's Bluetooth port.
- **Do:** Open. Look at LT1's IP Configuration for Bluetooth.
- **Expect:** Record whether the address shows there.
- **Result:**
  - bluetooth-address: the address shows nowhere. Desktop > IP Configuration lists only FastEthernet0 (Bluetooth isn't offered). Config > Bluetooth has Port Status (off), MAC 0002.BC31.9994, coverage range, discoverable, devices/pair/tether and beacon settings, but no IP fields. So set_ip on Bluetooth has nothing to show in the GUI; pktlib should probably refuse it.

## 15. far-coordinates (`out/pt-checks/15-far-coordinates.pkt`)

- **Why:** Negative and very large positions (pktlib writes 1234567.8, never 1.23457e+06).
- **Do:** Open. Zoom out; find NEG and FAR.
- **Expect:** Record where they land and whether the file loads at all.
- **Result:**
  - far-coordinates: file loads. PT clamps positions when it loads: NEG (-500, -300) became (99.5, 100), FAR (1234567.8, 100) became (3899.5, 100), MID (400, 300) became (399.5, 300). So the workspace runs from about x 100 to 3900 (y min 100), and PT saves x as n.5.

## 16. control-characters (`out/pt-checks/16-control-characters.pkt`)

- **Why:** A BEL in a banner, a tab and a control character in the user profile.
- **Do:** Open. On R1, `show banner motd`; Options > User Profile.
- **Expect:** Record what shows, and whether the file loads.
- **Result:**
  - control-characters: file loads. R1's MOTD shows at the console as 'line one' + a dot glyph + 'bell' (the BEL kept, drawn as a dot). User Profile: Name shows 'Name' + wide gap + 'with tab' (tab kept, shown as whitespace); Additional Info shows 'info' followed by a box/circle glyph for the control character. Nothing refused.
  - (re-save): profile name tab and info \x01 kept byte for byte; banner BEL kept (`banner motd #line one\x07bell#`).

## 17. rt02-deduplicated (`out/pt-checks/17-rt02-deduplicated.pkt`)

- **Why:** pktlib now keeps a command entered twice in a block once; rt02 lost a duplicate `network` line.
- **Do:** Open. On STB1, `show ip ospf neighbor` and `show ip route ospf`.
- **Expect:** Neighbours FULL and the inter-area routes there, as in the original check.
- **Result:**
  - rt02-deduplicated: (first refused as 'not compatible with this version': TS2's 2620XM serial was named Serial0/0/0; PT names it Serial0/0. Fixed on pt-results, rebuilt.) Rebuilt file opens. STB1 'show ip ospf neighbor': 1.1.1.1 FULL/ - on Serial0/0/0 (10.1.255.1). 'show ip route ospf': O IA routes to 1.1.1.1, 1.1.1.3, 1.1.1.10, 2.2.2.3, 4.4.4.4, 5.5.5.5, 10.0.0.0/4/8/12, 10.0.10.0, 10.3.255.0, 10.4.0.0, 10.4.1.0, 10.4.255.0, 10.5.255.0 and more (--More--). Inter-area routes there; the dropped duplicate network line changed nothing.

## 18. rt05-deduplicated (`out/pt-checks/18-rt05-deduplicated.pkt`)

- **Why:** rt05 lost a duplicate `no auto-summary`.
- **Do:** Open. On V6-B, `show ipv6 route` and `show ip route eigrp`.
- **Expect:** OSPFv3 and EIGRP routes learned, as in the original check.
- **Result:**
  - rt05-deduplicated: V6-B 'show ipv6 route': 16 entries; O 2001:DB8:1::/64, 3::/64, 6:2::/64 (OSPFv3, via FE80::1 Gi0/0/1) and D 2001:DB8:4::/64 (Serial0/1/1), 5::/64 (Gi0/0/2) (EIGRPv6), plus C/L. 'show ip route eigrp': D 10.6.0.16/30, D 192.168.4.0/24 (Serial0/1/1), D 192.168.5.0/24. OSPFv3 and EIGRP both learned; the dropped duplicate 'no auto-summary' changed nothing.

## 19. rt05-blocks-merged (`out/pt-checks/19-rt05-blocks-merged.pkt`)

- **Why:** If a second `ipv6 router ospf 1` merges into the first (as IOS would), pktlib can make config fully idempotent.
- **Do:** Open. On V6-A and V6-B, `show running-config | section ipv6 router` and `show ipv6 route ospf`.
- **Expect:** One block each, and the OSPFv3 routes still learned. If so, the merge goes in.
- **Result:**
  - rt05-blocks-merged: opens. V6-A 'show ipv6 route ospf': O 2001:DB8:3::/64, 6:3::/64 and OE2 4::, 5::, 6:4::, 6:5::, 6:6:: (tag 1) learned. V6-B: O 1::, 3::, 6:2::, FFFF::1/128. PT's re-save shows ONE `ipv6 router ospf 1` block on each router, so the merge can go in. (`show running-config` needs enable, so the block count comes from the re-save.)
  - / 18 NEW FINDING: PT drops two IPv6 routing lines in BOTH 18 (unmerged) and 19 (merged), so it isn't the merge: V6-A `ipv6 router ospf 1` / `default-information originate always` (gone from the re-save; no ::/0 in V6-B's IPv6 table), and V6-B `ipv6 router eigrp 200` / `redistribute ospf 1 metric 1544 20000 255 1 1500 include-connected` (gone). PT also adds `log-adjacency-changes` under ipv6 router ospf. Candidates for refused().

## 20. sw01-port-channels-in-order (`out/pt-checks/20-sw01-port-channels-in-order.pkt`)

- **Why:** pktlib now writes Port-channel blocks in number order (Po1, Po2, ...); sw01 had them reversed when it was checked.
- **Do:** Open. On CORE1 and CORE2, `show etherchannel summary`.
- **Expect:** All five channels (SU) on CORE1 and three on CORE2, as in the original check.
- **Result:**
  - sw01-port-channels-in-order: CORE1 'show etherchannel summary': 5 groups, 5 aggregators: Po1(SU) LACP Gi1/0/23-24, Po2(SU) PAgP Gi1/0/1-2, Po3(SU) LACP Gi1/0/19-20, Po4(SU) on Gi1/0/3-4, Po5(RU) LACP Gi1/1/1-2, all ports (P). CORE2: 3 groups: Po1(SU) LACP, Po3(RU) LACP, Po5(RU) LACP, all (P). OSPF FULL with 2.2.2.2/1.1.1.1 over Po3 and Po5. All channels up with Port-channels written in number order. (Note: CORE1 shows Po3 as SU (layer 2) while CORE2 shows Po3 as RU (layer 3).)

## 21. global-lines-pktlib-order (`out/pt-checks/21-global-lines-pktlib-order.pkt`)

- **Why:** pktlib writes `username`, `ip domain-name` and `ip ssh version 2` after `line vty`; IOS saves them near the top. Compare with the next file.
- **Do:** Open. From PC1, `ssh -l admin 10.0.0.1` (password cisco). On R1, `show running-config`.
- **Expect:** SSH works. Note where Packet Tracer shows those lines after it loads the file.
- **Result:**
  - global-lines-pktlib-order: SSH from PC1 (admin/cisco) works: R1>. PT's re-save moves the lines up: `username admin secret 5 ...` after `no ipv6 cef` and before `license udi`; `ip ssh version 2` then `ip domain-name lab.local` after license udi and before `spanning-tree mode pvst`; all above the first interface.

## 22. global-lines-ios-order (`out/pt-checks/22-global-lines-ios-order.pkt`)

- **Why:** The same router with those lines where IOS saves them.
- **Do:** Same as the previous check.
- **Expect:** SSH works. If both work, pktlib can switch to IOS order; if only one does, that's the order to use.
- **Result:**
  - global-lines-ios-order: SSH works too: R1>. PT's re-save is identical to 21's (same order). Both orders work, so pktlib can switch to IOS order. PT's own order: hostname, ip cef, no ipv6 cef, username, license udi, ip ssh version 2, ip domain-name, spanning-tree mode, interfaces.

## 23. pc-ipv6-sample (no file)

- **Why:** pktlib can't set a PC's IPv6 address yet: the template's IPV6_ADDRESSES list is empty, so the format of an entry is unknown.
- **Do:** In Packet Tracer itself: add a PC-PT, set IPv6 Configuration to Static, address 2001:db8:1::10/64, gateway 2001:db8:1::1; add a second PC set to Automatic (SLAAC). Save as pc-ipv6.pkt.
- **Expect:** Send pc-ipv6.pkt back: its XML shows how to write IPv6 on end devices.
- **Result:**
  - pc-ipv6-sample: done in PT's IP Configuration dialog on two pktlib-made PCs, saved as tests/fixtures/pc-ipv6.pkt. PC0 static 2001:db8:1::10/64 gw 2001:db8:1::1: port has IPV6_ADDRESSES/IPV6_ADDRESS {ADDRESS 2001:DB8:1::10, PREFIX 64, TYPE 0}, IPV6_ENABLED false, IPV6_ADDRESS_AUTOCONFIG false; the gateway is in the engine (GATEWAYV6 / IPV6_PORT_GATEWAY). PC1 Automatic (SLAAC): IPV6_ADDRESSES empty, IPV6_ENABLED true, IPV6_ADDRESS_AUTOCONFIG true ('Ipv6 request failed' in the dialog: no router on the LAN).

## 24. hub-card-removed (no file)

- **Why:** pktlib refuses to pull a middle card from a Hub-PT because it doesn't know the names after.
- **Do:** In Packet Tracer itself: add a Hub-PT, power it off, remove the card in the third slot, power on, and hover over the hub to read its port names. Same for a Switch-PT.
- **Expect:** Record the port names, in order.
- **Result:**
  - hub-card-removed: done in the GUI on a pktlib-made Hub-PT and Switch-PT (both with cards in slots 0-5): power off, drag the card out of slot 2, power on, hover. Hub-PT hover: FastEthernet0, FastEthernet1, FastEthernet3, FastEthernet4, FastEthernet5 (2 missing; nothing renumbered). Switch-PT hover: FastEthernet0/1, 1/1, 3/1, 4/1, 5/1 (2/1 missing). So both name ports by SLOT, not by counting. BUG: pktlib reads PT's own saved hub as FastEthernet0..4 (counting), wrong for 3 of the 5 ports; Switch-PT reads right. Saved as tests/fixtures/hub-card-removed.pkt (slot 2 empty on both). Once Hub-PT is named by slot, remove_module's refusal can go.

## 25. ccna-examples (no file)

- **Why:** 19 CCNA examples, built and audited but never opened in Packet Tracer.
- **Do:** Run `uv run python scripts/examples.py build`. Open each out/examples/ccna/*.pkt, follow the 'Check in Packet Tracer' list in its script's docstring, and click every scenario in the PDU list.
- **Expect:** Every scenario does what its name says (the ones named 'should FAIL' fail). Note each one that doesn't, with the example's name.
- **Result:**
  - ccna acl: Staff to the file server Successful; Guest to its gateway Successful; Contractor to the file server: should FAIL Failed; Staff ping into the guest LAN: should FAIL Failed; Guest to the file server: should FAIL Failed. All as named.
  - ccna dhcp: Relayed DHCP client to the HQ server Successful; Local DHCP client to the branch printer Successful; Relayed DHCP client on its own LAN Successful. All as named.
  - ccna dhcp_snooping: DHCP client out through the real gateway (PC1, PC3 to INTERNET) both Successful; DHCP client to its real gateway (PC2 to R1) Successful. All as named.
  - ccna eigrp: Across EIGRP (PC1 to PC3, PC2 to PC3) both Successful; Back the other way (PC3 to PC1) Successful. All as named.
  - ccna etherchannel: Across both EtherChannels Successful; Same VLAN across both EtherChannels Successful; Over the PAgP channel to the gateway Successful. All as named.
  - ccna hsrp: Out through the HSRP gateway: PC3 Successful; PC1 Failed on the first two fires, then Successful on the next three (first pings lost while ARP filled). The virtual gateway answers (PC2 to R1) Successful. All as named once warmed up.
  - ccna intervlan_mls: Between VLANs through the SVIs (STAFF1 to STUDENT2, STUDENT to PRINTER2) both Successful; Out the routed port to EDGE (STAFF2 to SERVER) Successful. All as named.
  - ccna ipv6: 'Across OSPF and the static routes' (PC1 to PC3 192.168.3.10) FAILED on every fire. Cause: R3 g0/2 is given 10.0.23.3/30, the BROADCAST address of 10.0.23.0/30. PT silently refuses it (R3 'show ip interface brief': Gi0/2 unassigned, up; no default route installed), so nothing gets back from R3's LAN. R1 has S 192.168.3.0/24 via 10.0.12.2 and its own ping to 192.168.3.10 is 0/5. Fix: R3 10.0.23.1/30 and R2's 'ip route 192.168.3.0 ... 10.0.23.1'. pktlib (and the audit) should refuse or flag a network or broadcast address on a router interface (see check 6).
  - ccna ipv6 (cont.): 'Branch default route to R2' (PC3 to PC2) FAILED x3, same cause (R3 has no IPv4 address toward R2); 'Across OSPF' (PC2 to PC1) Successful.
  - ccna nat: Office out through PAT Successful; Lab out through the dynamic pool Successful; Internet to WEB through static NAT Successful; Internet to a private address: should FAIL Failed. All as named.
  - ccna ospf_dr_election: Across the DR segment (PC-R4 to PC-R1, PC-R3 to PC-R2) both Successful; DR LAN to the priority 0 router (PC-R1 to PC-R4) Successful. All as named.
  - ccna ospf_multi_area: Across OSPF areas Successful; Area 2 to the backbone Successful; Area 1 to the backbone Successful. All as named.
  - ccna ospf_single_area: Across OSPF area 0 (PC2-1 to PC3-1, PC3-2 to PC1-2) both Successful; Default route learned from OSPF (PC2-1, PC3-1 to INTERNET) both Successful. All as named.
  - ccna port_security: Sticky MAC port to the server Successful; Static MAC port to the server Successful; Rogue PC to the server: should FAIL Failed. All as named.
  - ccna ripv2: Across RIP, LAN to LAN (PC1-1 to PC3-1, PC1-2 to PC3-2) both Successful; To R2 loopback (PC3-2 to R2) Successful. All as named.
  - ccna ssh: Admin to the router it will SSH to Successful; Admin to the switch management address Successful; Admin to the user LAN Successful. All as named.
  - ccna static_routes: Branch to HQ over static routes Successful; Branch to internet over two default routes Successful; HQ to internet over the default route Successful. All as named.
  - ccna stp: Same VLAN on the access switch Successful; VLAN 10 to VLAN 20 across the tree Successful; VLAN 20 to its root and gateway Successful. All as named.
  - ccna vlans_trunks: Same VLAN across the trunk Successful; Between VLANs through R1 Successful; VLAN 30 not on the trunk: should FAIL Failed. All as named.
  - ccna voice_cme: Desk PC through its phone to the server (DESK1, DESK4 to SERVER) both Successful; Data VLAN to the voice VLAN gateway (DESK3 to CME) Successful. All as named.
  - SUMMARY: 19 examples, 60 PDUs fired (each 2-3 times). 18 examples do exactly what their scenario names say (every 'should FAIL' fails). ipv6 fails 2 of 3 scenarios because R3 g0/2 has the /30's broadcast address (see above). hsrp's PC1 needed a third fire (ARP). The docstrings' show commands were not run (the PDUs cover reachability).

## 26. fault-lab (no file)

- **Why:** From TODO.md: the fault lab has never been opened.
- **Do:** Run `uv run python examples/labs/fault_lab.py`, open fault_lab.pkt and fault_lab_solution.pkt.
- **Expect:** Student file: Sales2 can't reach Sales1, Tech1 can't reach its gateway. Solution: every PDU in the scenarios succeeds.
- **Result:**
  - fault-lab: student fault_lab.pkt: 'Sales2 to Sales1' Failed (the VLAN fault shows); 'Tech1 to its gateway' SUCCESSFUL, not Failed; 'Sales to Tech (routed on R1)' (Sales1 to Tech2) Successful. Solution: all three Successful. FINDING (example, not PT): the Tech1 PDU pings R1 on Tech1's own subnet, where the default gateway is never used, so the wrong-gateway fault can't show in it. Ping something off Tech1's subnet (e.g. Tech1 to Sales1) to make that scenario fail in the student file.

## 27. enterprise-link-local (no file)

- **Why:** From TODO.md: cloned PCs now get their own IPv6 link-local.
- **Do:** Run `uv run python examples/showcase/enterprise.py`, open it, `ipconfig` on STAFF1.
- **Expect:** Link-local FE80::202:BAFF:FE64:6A24, not FE80::290:CFF:FEC7:8E5A.
- **Result:**
  - enterprise-link-local: STAFF1's IP Configuration shows Link Local FE80::202:20FF:FEAE:A711, which is the EUI-64 of its own MAC 0002.20AE.A711 in this build (the checklist's FE80::202:BAFF:FE64:6A24 came from an older build with other MACs). Not the template's FE80::290:CFF:FEC7:8E5A, so the fix holds in the GUI.

## 28. pka-sample (extra, asked for from the Mac)

- **Result:**
  - PKA sample (extra, from the Mac): tests/fixtures/sample.pka plus its answer network as plain tests/fixtures/sample-answer.pkt (pktlib-built: 2911 R1 + PC1, R1 G0/0 10.0.0.1/24, PC1 10.0.0.10/24 gw 10.0.0.1). Made with Extensions > Activity Wizard: 'use the current network as the answer network' Yes; Instructions: "Give R1 G0/0 the address 10.0.0.1/24 and PC1 the address 10.0.0.10/24 with gateway 10.0.0.1."; Answer Network assessment items (5): PC1 Default Gateway 10.0.0.1, PC1 FastEthernet0 IP Address 10.0.0.10, Subnet Mask 255.255.255.0, R1 Host Name R1, R1 GigabitEthernet0/0 IP Address 10.0.0.1; Initial Network: Copy from Answer Network, then PC1's IPv4/mask/gateway cleared and R1 `hostname Router` + `no ip address` on g0/0; Save As .pka. pktlib.decode() reads it as is (same encryption): root <PACKETTRACER5_ACTIVITY> with its own VERSION 8.2.0.0162, a <PACKETTRACER5> inside, 3 <NETWORK> blocks, and ACTIVITY / ANSWER_TREE_CHECK_BOX / ANSWER_TREE_SELECTED / COMPARISONS / INITIALSETUP elements. No password set.
