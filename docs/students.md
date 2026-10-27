# For students

Check your college's rules on tools before using pktlib on assessed work. Checking your own
file is one thing. Generating the file you hand in is another, and most briefs expect you to
build it yourself.

## Check a lab before you hand it in

```
pktlib audit mylab.pkt
```

It finds what costs marks and is hard to spot by eye:

- duplicate IP or MAC addresses;
- PC gateways no router owns, or outside the PC's subnet;
- cabled ports left shut down;
- serial DCE ends with no clock rate;
- the two ends of a link in different subnets;
- routers with no routing;
- shared OSPF router-ids;
- config Packet Tracer silently drops when it opens the file.

It reads the file only. A clean audit doesn't prove a ping works, so still test in Packet
Tracer.

## See what's in a file

- `pktlib info mylab.pkt` lists the devices, links and addresses.
- `pktlib dump mylab.pkt` turns any `.pkt` into a Python script that rebuilds it.

## Practise

`python examples/labs/practice_lab.py` (from a clone of the repo) makes a random routing lab with
the routers left blank, plus an answer key to check against afterwards. Give it a number to
get the same lab again.
