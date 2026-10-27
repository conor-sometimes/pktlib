# Packet Tracer notes

What pktlib knows about Packet Tracer 8.2, and how it was found out. The rule behind all of
it: a behaviour counts as known only when it was seen in Packet Tracer itself.

## Editions

A .pkt carries one version stamp, `PACKETTRACER5/VERSION`, like `8.2.0.0162`
(major.minor.patch.build). Packet Tracer checks it when it opens a file. Tried
on 8.2.0: a newer stamp is refused, even a later patch (8.2.2), with "This file
requires Cisco Packet Tracer version ..."; an older one (8.1.1) opens; a stamp
that isn't a version is refused.

pktlib treats it like Rust editions. `pktlib.new(edition="8.2")` (the default
is `pktlib.LATEST`) stamps a release pktlib has templates and tested quirks
for, and any other edition is an error, so pktlib can't write a file for a
Packet Tracer nobody has checked it against. `pktlib.EDITIONS` lists them (one
so far). `net.version` and `net.edition` tell you what you loaded.

`pktlib.load()` refuses a file from a newer Packet Tracer, or one with a stamp
that isn't a version, as Packet Tracer would; `load(path, strict=False)` reads
it anyway and keeps its stamp. Saving an older file stamps it with the newest
edition, which is what Packet Tracer 8.2 does when it saves one.
`pktlib info` reads any version and says which edition it is.

**Files from before Packet Tracer 8** (found with a 6.2 starter file a lecturer
handed out) load and convert: their raw `^C` banner bytes are kept, cables
that point at a device's position are repointed at a SAVE_REF_ID, and saving
writes an 8.2 file that Packet Tracer opens and runs. Their physical workspace
is laid out the old way, so adding devices is refused until the file has been
opened in Packet Tracer 8.2 and saved once.

## Device models and the spec

`src/pktlib/spec/devices.json` records, for every model in the Packet Tracer
8.2 palette (network devices and end devices), its kind, whether it runs IOS,
and its cable ports by name. Names come from Packet Tracer itself, three ways:
the device's own `interface` list (`ios-config`); its cable menu read by hand
(`pt-menu`: the 7960 IP phone's ports are `Switch` and `PC`); or its hover
table, every name matched to its port in the file by MAC address
(`pt-hover`: this found the IE-2000's first four ports have no type in the
template, and that IOx routers hide ports PT never lists). All 64 models in
the 8.2 palette are verified; `pktlib.models()` lists them. Home kit keeps its
GUI names, spaces and all (`wrt["Ethernet 1"]`, `meraki["Internet 1"]`,
`cloud["Coaxial7"]`). The Meraki MX65W, like the 3702i and LAP-PT, ships
with its power adapter fitted (off the palette it's switched off).
`unverified=True` stays for models a later edition adds.

The cable `connect()` picks is the one Packet Tracer brings the link up on,
checked device by device: switch-like FastEthernet ports (switches, hubs, the
Sniffer, modems' LAN side, the cloud, a home router's LAN ports) take straight; hosts,
routers, access points and a home router's Internet port take cross-over;
gigabit ports came up on either.

pktlib won't cable a port Packet Tracer can't name (a radio, or a port with no
type): a cable whose port PT doesn't know makes it refuse the whole file as
"not compatible with this version".

`tests/test_spec.py` builds each verified model fresh, saves, reloads, and
checks pktlib's port names against the spec.

## What Packet Tracer does that pktlib handles for you

Found the hard way while testing the examples:

- **Config is replayed on open.** A router's running-config text in the file
  is run as IOS commands when Packet Tracer loads it, so plain config works
  (abbreviations included). Port IP fields are ignored for IOS devices. pktlib writes it
  the way IOS saves it: no `exit` or `end` lines, tabs as spaces.
- **`interface range` is ignored on load.** pktlib expands ranges into one
  block per interface before writing.
- **VLANs live in a VLAN database, not the config.** `vlan N` lines go there;
  `switchport access vlan N` creates N if it's missing, as real IOS does.
- **Every device needs its own MACs,** including the base address switches use
  as their bridge ID and SVI MAC. Cloned devices sharing one broke STP, ARP and
  HSRP between two cores. pktlib gives every MAC in a new device a fresh value,
  and re-derives the IPv6 link-local Packet Tracer stores beside it (EUI-64 of
  the MAC); left alone, every PC showed the template's.
- **Order matters for IPv6.** `ipv6 unicast-routing` has to come before the
  interfaces: written near the end, Packet Tracer refused every `ipv6 ospf` and
  `ipv6 eigrp` interface line. pktlib puts it ahead of the first interface.
- **An RSA key isn't config.** `crypto key generate rsa` is typed, never saved
  in `show run`; Packet Tracer keeps the key in the device's SECURITY section.
  `generate_rsa_key` writes one there, and SSH logins to it work.
- **Names before the interfaces that use them.** IOS refuses a
  `zone-member security` line for a zone that doesn't exist yet, and saves
  zones, IPS rules and crypto maps above the interfaces. pktlib puts new
  crypto, class-map, policy-map, zone and `ip ips` blocks ahead of the first
  interface; a file built that way loaded in Packet Tracer with every line kept.
- **A voice VLAN must exist.** `switchport voice vlan N` creates VLAN N in the
  database, as `switchport access vlan` does; without it 24 phones stayed
  unregistered.
- **Home routers aren't IOS.** The Linksys, HomeRouter-PT-AC, DLC100 and the
  central office server ignore IOS text in the file, so `config()` on them
  raises instead of writing something that does nothing.
- **The AccessPoint-PT-AC's stock card is gigabit-only.** Its
  PT-REPEATER-NM-1CGE stays red to any FastEthernet port (a PC, a switch's
  Fa0/1) on either cable and comes up to a gigabit port. Swap in
  PT-REPEATER-NM-1CFE (`remove_module`, `add_module`) and it links to a PC on
  a straight cable. The audit flags the stock card cabled to anything slower;
  `port.module` says which card a port sits on.
- **Some IOS is refused silently on load.** `default-information originate`
  with `metric` or `metric-type` is rejected, so no default is sent; the rest
  of the config still runs. `refused()`, the audit and a `PktWarning` from `config()` flag
  known cases.
- **The 3650 ships with no power supply** and never boots; pktlib's template
  has an AC-POWER-SUPPLY fitted. Likewise the 3702i and LAP-PT access points
  ship without their power adapter (the port never comes up); theirs have
  ACCESS_POINT_POWER_ADAPTER fitted.
- **Routers, 3560s and 3650s ship with `no cdp run`.** IP phones learn their
  voice VLAN over CDP, so a phone's access switch needs `cdp run`.
- **Packet Tracer is fussy about where config sits.** A `channel-group` in a
  second copy of an interface block is dropped on load. An `interface
  Port-channel` written after its member ports lets the channel form, but a
  later `router ospf` silently vanishes. So `config()` writes as IOS saves:
  commands go into the interface's existing block (replacing its `shutdown` or
  `no ip address`), and a Port-channel goes ahead of the ports. The
  data-centre cores run an LACP channel this way.

## How the file format works

1. byte-reverse the file and XOR each byte with `(L - i*L) & 0xFF`, L = length
2. Twofish in EAX mode, key sixteen `0x89`, nonce sixteen `0x10`, 16-byte tag at the end
3. XOR each byte with `(n - i) & 0xFF`, n = plaintext length
4. Qt `qCompress`: a 4-byte big-endian length, then zlib, giving the XML

Worked out by the [pka2xml](https://github.com/mircodz/pka2xml) project.
pktlib re-implements it in Python and checks Twofish against the paper's test
vectors.

## Templates

New devices are copies of devices Packet Tracer itself made, kept in
`src/pktlib/data/`. They come from `scripts/sources/*.pkt` (one of every
palette device, saved by 8.2.0); `just refresh` re-extracts them and rebuilds
the spec.
