# Notes for agents working on pktlib

pktlib reads, edits and writes Cisco Packet Tracer `.pkt` files in plain Python. Read
`README.md` first, then `docs/guide.md` (the API, errors and warnings) and
`docs/packet-tracer.md` (editions, the spec, the quirks pktlib handles), then `TODO.md` for
where work stands. `CHANGELOG.md` gets a line for anything a user would notice.

The one rule behind everything here: **Packet Tracer is the source of truth.** A behaviour
counts as known only when it was seen in Packet Tracer 8.2.0 (build 8.2.0.0162). Tests pin
what was seen, with the date and what was tried, in the docstring. Don't add a rule, a port
name, a cable choice or a "refused" line from memory or from real-IOS knowledge alone.

## Layout

- `src/pktlib/`
  - `codec.py`, `twofish.py`: the file encryption and compression (`decode`/`encode`).
  - `model.py`: `Network`, `Device`, `Port`, `Link`. Building, cabling, modules, VLANs, config.
  - `iosconfig.py`: reading IOS text and `merge_config` (writes config the way IOS saves it;
    Packet Tracer replays it top to bottom on open, so order matters), `refused()`.
  - `editions.py`: which Packet Tracer a file is for (the `PACKETTRACER5/VERSION` stamp).
  - `ports.py`, `modules.py`, `shapes.py`, `export.py` (`to_python`), `cli.py`.
  - `data/`: device templates and the module catalogue, generated. Don't edit by hand.
  - `spec/devices.json`: every palette model's ports, slots and accepted modules. Generated.
- `scripts/`
  - `sources/*.pkt`: files Packet Tracer itself saved, one of every device. Templates and
    the spec come from these.
  - `make_templates.py`, then `make_spec.py` (`just refresh`). `make_spec.py` holds the
    evidence read off the GUI by hand: `HOVER` (names from hover tables and cable menus),
    `MANUAL`, `ACCEPTS` (Physical-tab module lists).
- `tests/`: pytest plus hypothesis. `just test` (about a minute: every core, in a random order, warnings are errors), `just quick`. Random tests
  take their example counts from `examples(n)` in conftest, times `PKTLIB_SCALE`: `just fuzz`
  is 20 times, and `just soak HOURS` runs the state machine, the damaged-file fuzzer and the
  property tests on every core but two (`scripts/soak.py`; counts and failure logs in
  `soak/`). A failing case Hypothesis finds is replayed by the next `uv run pytest`.
- `docs/`: the guide, Packet Tracer notes, student and lecturer pages, examples table. The
  Python in them is run by `tests/test_docs.py`.
- `examples/`: networks to copy from, most opened and tested in Packet Tracer (the table in
  `docs/examples.md` says which).
- `stress/`: deliberately hard networks written to break pktlib. `just stress` rebuilds and
  audits them.

## Running things

- `uv sync`, then `uv run pytest`. If `uv` isn't on PATH (Windows), use
  `.venv\Scripts\python.exe` directly. `just` may not be installed; the justfile still
  documents every command.
- The test suite must pass before any commit. `just check` runs lint (ruff; ty; mypy --strict, pyright and pyright --verifytypes on the package) and the
  tests.
- `tests/test_golden.py` builds every example and stress script with a fixed seed and compares
  the XML with `tests/golden.json`. A refactor must leave it unchanged. When output is meant to
  change, diff the decoded files first, then re-record with `PKTLIB_UPDATE_GOLDEN=1 uv run pytest -n0
  tests/test_golden.py` (one process: workers would each write part of the file).

## Generating .pkt files

- Write a script, not a one-off: build with the API, save the `.pkt` next to the script (or
  into `out/`), run `pktlib audit` on it, and fix what it reports.
- `.pkt` files are git-ignored except `scripts/sources/` and `tests/fixtures/`.
  Commit the script; the file can be rebuilt.
- A file saved in Packet Tracer carries the saver's recent-files list (Windows username,
  folders, other file names), and 8.2 can't clear it. Empty every `RECENT_FILES` before
  committing a sample or fixture; `tests/test_model.py` fails if one isn't.
- Never commit a file from a course: no lecturer starter file, assessment or NetAcad
  activity, not even cut down. Read one for its quirks, pin the quirk in a test, keep the
  file out. Every sample gets a line in `tests/fixtures/README.md` saying where it came
  from; `tests/test_model.py` fails on one that hasn't.
- Use verified models only (`pktlib.models()`, all 64 in 8.2). Use the port names the spec
  gives, which are Packet Tracer's own, including home-kit names with spaces
  (`wrt["Ethernet 1"]`, `cloud["Coaxial7"]`). A cable whose port name Packet Tracer doesn't
  know makes it refuse the whole file.
- Let `connect()` pick the cable unless you are testing cables. Its choices were each seen
  bringing a link up.
- Put config in with `config()`; it merges into existing blocks and keeps
  Packet Tracer's ordering rules. Don't write `running_config` by hand.
- Don't call `config()` on home routers or the central office server: Packet Tracer ignores
  IOS there, and pktlib raises.
- New Packet Tracer quirk found? Add a test that pins it, a line in the quirks list in
  `docs/packet-tracer.md`,
  and (if it's a config line Packet Tracer silently drops) a `refused()` rule.

## Checking in Packet Tracer

A change that affects what Packet Tracer does isn't done until it has been opened there:
- the file loads ("not compatible with this version" means a bad port name or version stamp);
- the links come up;
- the `show` command or ping that proves it works.

Useful evidence sources:
- The **hover table**: point at a device to see each port's name and MAC. Match MACs to the
  file to tie names to ports.
- The **cable menu**: pick a cable, click a device, and every cable port is listed in file
  order.
- The **Physical tab**: shows a device's module list.

When driving Packet Tracer with computer use on this machine:
- Screenshots can land on the wrong monitor; switch to the one showing Packet Tracer. Wait about 5 s after
  opening a device window.
- Never `open_application` to recover focus, because it starts another Packet Tracer.
  Bring the window forward instead.
- Paste router CLI with the CLI's Paste button. On a PC prompt, type word by word.
- The 3650 has no `ping ... source`. Serial cables draw as red zigzags; that's normal.
- Decline the Network Controller's external-access prompt.

## Editions

`pktlib.new(edition=...)` only accepts releases pktlib was tested on (just "8.2"). Adding an
edition means new `scripts/sources/` saved by that release, regenerated templates and spec,
the quirks re-checked, and the examples re-run there. Don't add a version string alone.

## Style

- Plain, short comments and docstrings, saying what Packet Tracer does and how we know.
- No em or en dashes in committed files.
- No AI attribution lines in commit messages or pull requests.
- `main` takes changes only through pull requests: work on a branch, push it, open a PR, and
  squash-merge it once lint and the four test jobs pass (GitHub signs the squash commit, so it
  shows Verified). No force-pushes to `main`.
- Commit as `conor.d.mcshane@outlook.com` (the email on the signing key, so GitHub shows
  Verified), and push with `gh`/git as
  set up.
