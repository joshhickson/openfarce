# Labs

Eight exercises that use one rig: eight MicroSD cards, eight USB readers, a
powered hub and a Raspberry Pi. Addendum A2.4.1.

They are written for someone who has used a terminal and has not necessarily
built a RAID. Every command is meant to be typed, and every lab ends with a
question that the commands alone do not answer.

| | Lab | Status |
|---|---|---|
| 1 | [Eight block devices](01-block-devices.md) | complete |
| 2 | [RAID 0 against RAID 1](02-raid-0-vs-1.md) | complete |
| 3 | [Failure and rebuild](03-failure-and-rebuild.md) | complete |
| 4 | Latency against bandwidth | outline |
| 5 | Swap and memory pressure | outline |
| 6 | Thermal throttling | outline |
| 7 | Wear and write amplification | outline |
| 8 | A language model as the workload | outline |

Labs 4–8 are [outlined here](04-08-outlines.md). They are outlines because they
have not been run on hardware, and a lab that has not been run is a guess about
what the commands will print.

## Before any of them

The cards get erased. Repeatedly. Do not put a card in this rig that has
anything on it you want.

Everything below assumes `sudo` and a rig that enumerates. Check with:

```bash
python3 -m farce.enumerate --check
```
