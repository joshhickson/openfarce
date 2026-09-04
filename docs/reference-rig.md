# Building the reference rig

Written so that someone who has never seen the machine can reproduce it. If a
step here is unclear or missing, that is a bug in this document — open an issue.

**This document is out of character.** The campaign page is satire; this is the
build guide, and it is straight.

---

## Two rigs, and which one this is

**The reference rig is eight lanes on a Raspberry Pi.** Eight 16 GB MicroSD
cards in eight USB readers on one powered hub, striped into a RAID 0 span and
enabled as Linux swap. 128 GB raw. About $70 of parts. This is the machine that
gets built, and every measurement published by this project comes from it until
something bigger exists.

**The 40-lane array is a stretch goal**, not a prerequisite. It is the same
procedure at five times the scale, and the differences are called out in
"Scaling to forty" below. It costs roughly $900 and nobody has built one.

Both page a language model larger than host RAM onto the array and measure the
result. It will be slow. That is the measurement, not a failure.

Every artifact the tools write carries the lane count it was measured on, so a
number from one rig cannot be quoted as a number from the other. See
`farce/rig.py`.

## Parts — the reference rig

| Qty | Item | Notes |
|---:|---|---|
| 1 | Raspberry Pi 4B | 8 GB strongly preferred. The 4 GB will work and swaps even on a 7B model. |
| 1 | Official 5.1 V / 3 A USB-C supply | Not a phone charger. An undervolted Pi fails in ways that look like card faults. |
| 1 | Boot MicroSD, ≥32 GB | **Not part of the array.** |
| 1 | 7-port powered USB 3.0 hub | Must be self-powered. The Pi delivers about 1.2 A across all its USB ports; eight writing readers want roughly that alone. |
| 8 | USB 3.0 single-slot MicroSD reader | All eight the same SKU. See "Readers that lie" below. |
| 8 | 16 GB MicroSD, UHS-I Class 10/A1 | Mixed brands acceptable — RAID 0 uses the smallest member's size on all eight, so an old 32 GB card contributes 16 GB. Drawers first. |
| 1 | USB 3.0 cable, hub to Pi | Usually supplied with the hub. |
| 1 | 40 mm 5 V fan | Not optional under sustained write. See "Airflow". |
| — | Printed blade and hub tray | Optional but tidy. `hardware/blade/`. |

The itemised, priced version is `campaign/reports/H-A2.1_RIG_SHOPPING_LIST.md`
in the campaign repository, generated from the same parts file that prices the
kits.

## Before you buy eight of anything

### Readers that lie

Some inexpensive USB card readers report the same `ID_SERIAL_SHORT` for every
unit in a production batch. Forty readers reporting one serial cannot be told
apart by serial, so `enumerate.py` falls back to USB topology alone — which
works, but means you can never move a reader to a different port without the
ledger treating it as a new device.

Buy **one** reader. Plug it in. Run:

```bash
udevadm info --query=property --name=/dev/sda | grep ID_SERIAL
```

Then plug in a second one of the same model and compare. If the serials match,
buy a different reader.

### One controller

**On the Pi 4B this is not avoidable and you should design around it.** Both
blue USB 3.0 ports hang off a single VL805 controller on a PCIe Gen 2 x1 link.
The real-world ceiling for everything on both ports together is about 350 MB/s.

Four UHS-I readers can saturate that. Eight cannot go faster — only wider. That
is not a flaw in the rig; it is the measurement, and Lab 4 is built on it.

Plug the hub into one USB 3.0 port and leave the other empty. A second hub on
the other port shares the same ceiling and the same power budget, and buys
nothing but confusion.

```bash
lsusb -t          # one 5000M bus on a Pi 4B; more on a desktop
```

On a desktop host building the 40-lane array, the same warning inverts: forty
readers behind one controller means every number you publish is a statement
about your motherboard. Use two or more independent controllers.

### Hub supplies

A ten-port hub sold with a 12 V 2.5 A supply cannot deliver full current to ten
active readers. The failure mode is not a clean error message: readers
enumerate, then silently drop off the bus under load, and `assemble.sh` refuses
to start with a missing-slot message that looks like a software fault.

If slots go missing under load and nothing else explains it, suspect the supply
before anything else.

### Airflow

Eight readers in a row with no moving air throttle within minutes of sustained
writing. A throttled card falls from around 104 MB/s to under 10, and because
RAID 0 waits for its slowest member, one hot card stalls the whole array.

A 40 mm 5 V fan off a spare hub port, blowing along the row, is enough. The
printed blade has a mount for one and open lattice sides for the same reason.
Do not put this in a box.

If you skip the fan, say so when you publish numbers, because the numbers will
be different and the difference is not small.

## Assembly

1. **Mount the readers.** Four rows of ten on the perfboards, cable-tied. Leave
   room to pull any single reader without disturbing its neighbours; you will be
   replacing dead cards.
2. **Label every port.** Write the hub number and port number next to each
   reader. When `assemble.sh` reports `MISSING usb_path=2-1.4.3`, you want to be
   able to walk to it.
3. **One hub per supply.** Do not daisy-chain hubs. Do not run two hubs from one
   supply through a splitter.
4. **Insert the cards last**, after the hubs are powered and stable.

## First run

```bash
sudo python3 -m farce.enumerate
```

Expect eight lines. If you see fewer, the missing readers are a hardware problem
and no amount of software will fix them.

```bash
sudo python3 -m farce.enumerate --expect 8     # writes /etc/farce/cards.json
sudo farce/assemble.sh                          # creates the array on first run
```

`assemble.sh` will refuse to proceed with fewer than `FARCE_LANES` readers
(default 8). This is
deliberate: a RAID 0 span created across thirty-nine devices is a different
array, and silently building it would invalidate every measurement afterwards.

Then measure, before you put any load on it:

```bash
sudo python3 -m farce.bench --all --allow-writes -o bench-day0.json
```

Keep that file. It is the baseline every later measurement is compared against,
and once the cards have worn you cannot recreate it.

## Running it

```bash
sudo systemctl enable --now farce-assemble.service
sudo systemctl enable --now farce-endure.service
sudo systemctl enable --now farce-thermal.service
```

Verify it survives a power cut, because it will have to:

```bash
sudo systemctl reboot
# ... after boot
journalctl -u farce-assemble -b | tail -20
swapon --show
```

You are looking for `8/8 readers present` and the array in `swapon --show`.

## Safety

Not optional reading. This rig runs unattended for months.

- **192 W of hub supplies.** Four 12 V 4 A bricks. Give them air and do not
  stack them.
- **After the first hour, touch everything.** Hubs, supplies, cards, cables.
  Nothing should be more than warm. A hot reader is a reader about to fail, and
  a hot supply is a fire risk.
- **Site it accordingly.** Hard surface, not carpet, not a bookshelf, not in a
  cupboard. It runs continuously and will be forgotten about.
- **Smoke detector in the room.** This is a homebuilt array of flash
  devices running at full duty cycle, continuously, for two months, with
  consumer power supplies. Treat it as you would a 3D printer.
- **The array will die.** That is the experiment. Put nothing on it you want.

## When a card fails

It will. RAID 0 has no redundancy, so the array dies with the first card.

```bash
sudo farce/assemble.sh --teardown
sudo python3 -m farce.enumerate --check     # names the dead slot
# replace the card, then
sudo farce/assemble.sh --create             # DESTROYS DATA, which is fine
```

The endurance ledger keeps the dead card's accumulated wear under its old key,
so the record of what it took to kill it survives the replacement.

## Scaling to forty

The 40-lane array is the same procedure with four differences, and it is a
stretch goal rather than a plan:

1. **Host.** A Pi cannot do it. Forty readers need a desktop with ≥32 GB RAM and
   ideally a PCIe USB card exposing two or more independent controllers, so the
   array is not one 5 Gbps uplink pretending to be forty lanes.
2. **Hubs.** Four 10-port powered hubs, each with a **12 V 4 A or better**
   supply. A ten-port hub sold with 2.5 A cannot feed ten active readers, and
   the failure looks like missing slots rather than a power fault.
3. **Staging.** `FARCE_STAGE_SIZE=8 FARCE_STAGE_DELAY=2` — forty readers
   powering up together pulls more than any of those supplies will deliver.
4. **Lane count.** `FARCE_LANES=40 FARCE_CARD_BYTES=32000000000`. Everything the
   tools write then carries `lanes: 40`, and no file from the two rigs can be
   confused for the other.

Cards are 32 GB in the 40-lane build, matching the Developer Kit, so the array
is 1.28 TB raw rather than 128 GB.

Nobody has built this. Every figure the site publishes for a 40-lane array is
the Feasibility Report's projection and is labelled as one.

## Publishing measurements

Numbers from this rig go on the campaign site. Two rules:

1. **Never publish a number from `simulate_rig.sh`.** Loop devices are not
   MicroSD cards.
2. **Never hand-type a number onto the site.** `bench.json` and `counter.json`
   are read programmatically. If a figure cannot be produced by a tool, it does
   not go on the page.
