# Packet Tracer checks, round 4

Done on Windows, Packet Tracer 8.2.0.0162, 24 Nov 2026, by Claude through computer use, on branch
round3-fixes. One file, built with pktlib: `net.switch("Switch 7")`, `net.router("Core (A)#1",
"2911")`, `net.pc("PC 7")`, and two `log_command()` entries on the router, `enable` at 3 Nov
09:05:01 (prompt `Core-A-1>`) and `sh ip int br` at 24 Nov 12:30:00 (resolved `show ip interface
brief`).

## 1. Spaced names (#11)

- The file opened without complaint. Workspace labels: `2960-24TT / Switch 7`, `2911 / Core
  (A)#1`, `PC-PT / PC 7`.
- The router's CLI prompt is `Core-A-1>`, then `Core-A-1#` after `en`: the hostname pktlib made
  from the name is the one IOS runs.
- Passed.

## 2. Command log written by pktlib

- Options > View Command Log listed both entries as written: `1  Tue Nov 3 09:05:01 2026  Core
  (A)#1  Core-A-1>  enable  enable` and `2  Tue Nov 24 12:30:00 2026  Core (A)#1  Core-A-1#  sh ip
  int br  show ip interface brief`. The unpadded day reads back.
- Typing `en` on the router added `3  Tue Nov 24 14:11:11 2026  Core (A)#1  Core-A-1>  en
  enable` after them. Packet Tracer's own entry uses the display name in the Device column, as
  `log_command()` does.
- Passed.
