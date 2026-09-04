# OpenFARCE

Tooling for a forty-slot MicroSD array used as swap-backed block storage.

**Status: pre-alpha.** Nothing here is finished, there is no release, and it is
not included in any F.A.R.C.E. Flash kit. The reference rig it is written for
has not been built yet, so no measurement in this repository has been taken
from real hardware.

---

## What this is

Forty consumer MicroSD cards, striped into a RAID 0 span, handed to the Linux
kernel as swap. A model larger than host RAM is then paged onto it.

That is the entire architecture. There is no custom driver, no kernel module,
and no clever I/O layer — the kernel does the paging and the array is a block
device it pages onto. What is here is the operational tooling around that:
bringing forty readers up reliably, measuring what they actually do, and
keeping an honest ledger of how fast the media is wearing out.

## What it is not

It is not RAM. It is not memory. It is swap on removable flash over USB, and
every document in this repository says so in those words. The campaign page
that links here calls it "system-addressable memory," which is a marketing
phrase meaning `free` prints the total in the swap row. It is not faster than
anything. Putting a working set on it makes a machine slower.

If you came here from the campaign page expecting an inference accelerator,
read [`docs/reference-rig.md`](docs/reference-rig.md) before spending money.

## Install

```bash
git clone https://github.com/joshhickson/openfarce
cd openfarce
sudo apt install mdadm fio python3 uhubctl      # uhubctl optional, see below
sudo mkdir -p /opt && sudo cp -r . /opt/openfarce
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Nothing is enabled by default. Enable the units once you have hardware and have
read the build guide.

## Use

```bash
# What is attached right now, by stable identity rather than /dev/sdX
sudo python3 -m farce.enumerate

# Bring the array up. Refuses a partial array and names the missing slot.
sudo farce/assemble.sh

# Measure it. Reads are safe; writes are destructive and opt-in.
sudo python3 -m farce.bench --all -o bench.json
sudo python3 -m farce.bench --all --allow-writes -o bench.json

# Start the endurance ledger
sudo systemctl enable --now farce-endure.service
sudo python3 -m farce.endure --status

# Run a model larger than host RAM
sudo farce/serve.sh --model /srv/models/llama-70b-Q4_K_M.gguf --json run.json
```

## No hardware?

```bash
sudo ./tools/simulate_rig.sh up 40
```

Forty loop devices, assembled the same way, so every code path can be
exercised. Loop devices on an SSD are thousands of times faster than MicroSD
and do not wear out, so **no number from a simulated rig may be published.**

```bash
sudo ./tools/simulate_rig.sh down
```

## Layout

| Path | |
|---|---|
| `farce/enumerate.py` | identify readers by USB topology and serial, never by `/dev/sdX` |
| `farce/assemble.sh` | staged power-up, RAID 0 assembly, `mkswap`, `swapon` |
| `farce/bench.py` | fio wrapper; per-card and aggregate; JSON out |
| `farce/endure.py` | write ledger and the days-remaining projection |
| `farce/thermal.py` | throughput-collapse detection, since MicroSD has no sensor |
| `farce/serve.sh` | llama.cpp launcher that pages onto the array |
| `tools/publish_counter.py` | push the counter to the site; refuses stale figures |
| `tools/simulate_rig.sh` | loop-device rig for development |
| `docs/reference-rig.md` | build guide |
| `docs/endurance.md` | what the counter measures and what it guesses |

## Two things that will bite you

**Kernel device names are not stable.** `/dev/sda` is whichever device
enumerated first, and that changes every boot and every time a hub comes up in
a different order. Everything here keys on `(usb_path, serial)` instead. If you
add code, do not reintroduce `/dev/sdX`.

**Cheap readers lie about their serial.** Some report an identical serial
across every unit in the batch, which makes them indistinguishable by serial
alone. `enumerate.py` warns and falls back to USB path, but then you must not
move readers between ports. Buy one reader before buying forty.

## Licence

MIT. See [LICENSE](LICENSE).
