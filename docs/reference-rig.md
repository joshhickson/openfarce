# Building the reference rig

Written so that someone who has never seen the machine can reproduce it. If a
step here is unclear or missing, that is a bug in this document — open an issue.

**This document is out of character.** The campaign page is satire; this is the
build guide, and it is straight.

---

## What you are building

Forty MicroSD cards in forty USB readers, on four powered hubs, striped into a
single RAID 0 span and enabled as Linux swap. A language model larger than host
RAM is then paged onto it, and the resulting speed is measured.

It will be slow. That is the measurement, not a failure.

## Parts

| Qty | Item | Notes |
|---:|---|---|
| 40 | 32 GB MicroSD, UHS-I Class 10 | Any major brand. All forty the same model — mixed cards make the array as slow as the slowest and confuse the endurance ledger. |
| 40 | USB 3.0 single-slot MicroSD reader | **Buy one first.** See "Readers that lie" below. |
| 4 | 10-port powered USB 3.0 hub | Supply must be **12 V 4 A or better**. This is the part people get wrong. |
| 4 | USB 3.0 cable | Type depends on the hub. |
| 5 | 7×9 cm perfboard | The readers mount to these so the thing is one object and not a nest. |
| 1 | Cable ties | You will use all of them. |
| 1 | Linux host, ≥32 GB RAM | A spare desktop. Not your daily machine — it will thrash. |
| 1 | PCIe USB 3.x card, ≥2 controllers | Optional. Strongly recommended; see "One controller" below. |

## Before you buy forty of anything

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

Forty readers behind a single USB 3.0 controller share one 5 Gbps uplink. At
that point you are measuring the controller, not the array, and every number
you publish will be a statement about your motherboard.

Four hubs on two or more independent controllers is the minimum useful topology.
Check what you have:

```bash
lsusb -t          # look at the number of distinct Bus lines with 5000M
```

### Hub supplies

A ten-port hub sold with a 12 V 2.5 A supply cannot deliver full current to ten
active readers. The failure mode is not a clean error message: readers
enumerate, then silently drop off the bus under load, and `assemble.sh` refuses
to start with a missing-slot message that looks like a software fault.

If slots go missing under load and nothing else explains it, suspect the supply
before anything else.

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

Expect forty lines. If you see fewer, the missing readers are a hardware problem
and no amount of software will fix them.

```bash
sudo python3 -m farce.enumerate --expect 40    # writes /etc/farce/cards.json
sudo farce/assemble.sh                          # creates the array on first run
```

`assemble.sh` will refuse to proceed with fewer than forty readers. This is
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

You are looking for `40/40 readers present` and the array in `swapon --show`.

## Safety

Not optional reading. This rig runs unattended for months.

- **192 W of hub supplies.** Four 12 V 4 A bricks. Give them air and do not
  stack them.
- **After the first hour, touch everything.** Hubs, supplies, cards, cables.
  Nothing should be more than warm. A hot reader is a reader about to fail, and
  a hot supply is a fire risk.
- **Site it accordingly.** Hard surface, not carpet, not a bookshelf, not in a
  cupboard. It runs continuously and will be forgotten about.
- **Smoke detector in the room.** This is a homebuilt array of forty flash
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

## Publishing measurements

Numbers from this rig go on the campaign site. Two rules:

1. **Never publish a number from `simulate_rig.sh`.** Loop devices are not
   MicroSD cards.
2. **Never hand-type a number onto the site.** `bench.json` and `counter.json`
   are read programmatically. If a figure cannot be produced by a tool, it does
   not go on the page.
