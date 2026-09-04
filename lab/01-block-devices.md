# Lab 1 — Eight block devices

**About 40 minutes.** You need the rig assembled and nothing else.

By the end you should be able to say what a block device is, why the kernel's
name for one is not a reliable way to refer to it, and roughly how fast a single
MicroSD card actually is as opposed to what the packet claims.

---

## 1.1 What the kernel sees

```bash
lsblk -o NAME,SIZE,TYPE,TRAN,MODEL
```

Eight removable USB devices, each a few gigabytes. Each is a **block device**:
something the kernel will read and write in fixed-size blocks, at an offset you
choose, in any order. That is the whole contract. A file is built on top of it,
and so is swap, and so is a RAID.

Look at the `NAME` column. Now:

```bash
sudo reboot
# ...and when it comes back
lsblk -o NAME,SIZE,TYPE,TRAN
```

**The names have probably moved.** `sda` and `sdc` may have swapped. Nothing is
wrong; `sd*` names are handed out in the order devices are found, and USB
enumeration order is not stable between boots.

This is not a trivium. A script that writes to `/dev/sdb` because that is what
it was last week will one day write to a different card, and if that card is the
one holding your data, the script will destroy it without erroring.

## 1.2 Names that do not move

Three stable ways to name the same device:

```bash
ls -l /dev/disk/by-id/ | grep usb
ls -l /dev/disk/by-path/ | grep usb
lsblk -o NAME,SERIAL,WWN
```

`by-path` is the USB topology: which port on which hub. It is stable as long as
nothing is physically re-plugged, and it is what `openfarce` uses:

```bash
python3 -m farce.enumerate
```

Read `farce/enumerate.py` and find where it decides on an identity. It keys on
the topology path rather than the serial number, and there is a comment saying
why. Cheap readers frequently ship with the same serial burned into every unit
in the batch — sometimes literally `000000000000`.

> **Check:** unplug one reader, plug it into a different hub port, and run
> `python3 -m farce.enumerate --check` again. What changed, and would a serial
> number have caught it?

## 1.3 One card, honestly measured

Pick a card. Confirm which one, twice, because the next command destroys it.

```bash
DEV=/dev/sdX          # <- set this yourself, after checking lsblk
lsblk -o NAME,SIZE,TRAN "$DEV"
```

Sequential read:

```bash
sudo fio --name=seqread --filename=$DEV --rw=read --bs=1M \
         --iodepth=8 --ioengine=libaio --direct=1 \
         --runtime=30 --time_based --group_reporting
```

Random 4 KiB read:

```bash
sudo fio --name=randread --filename=$DEV --rw=randread --bs=4k \
         --iodepth=32 --ioengine=libaio --direct=1 \
         --runtime=30 --time_based --group_reporting
```

Write down four numbers: sequential bandwidth, random IOPS, mean latency, and
99th-percentile latency.

`--direct=1` matters. Without it the kernel's page cache answers most of the
reads and you measure your RAM.

> **Check:** compare your sequential figure to the class rating printed on the
> card. Then compare your random-read figure to the sequential one. Which of the
> two numbers does a card manufacturer print on the packet, and why that one?

## 1.4 A filesystem, and the cost of one

```bash
sudo mkfs.ext4 -F $DEV            # destroys the card
sudo mkdir -p /mnt/lab1
sudo mount $DEV /mnt/lab1
df -h /mnt/lab1
```

Compare `df` against the size `lsblk` reported. Some capacity is gone — to the
filesystem's own metadata, and to the difference between a manufacturer's
gigabyte (10⁹ bytes) and the kernel's gibibyte (2³⁰).

Now the same random-read test through the filesystem instead of the raw device:

```bash
sudo fio --name=fsread --directory=/mnt/lab1 --size=512M --rw=randread \
         --bs=4k --iodepth=32 --ioengine=libaio --direct=1 \
         --runtime=30 --time_based --group_reporting
```

```bash
sudo umount /mnt/lab1
```

> **Check:** the filesystem run is slower than the raw-device run. Name two
> things the filesystem has to do on each read that the raw device does not.

---

## What you should be able to answer

1. Why is `/dev/sdb` an unsafe way to refer to a specific card?
2. Your card's sequential read is many times its random read. What is physically
   different about the two workloads?
3. If you joined all eight of these into one device, which of your four measured
   numbers would you expect to improve, and which would not?

Question 3 is Lab 2.
