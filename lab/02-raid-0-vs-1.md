# Lab 2 — RAID 0 against RAID 1

**About an hour.** Lab 1 first.

You will build the same eight cards two different ways, measure both, and find
that one of them is faster at everything and the other one survives a card
failure. There is no configuration that is both.

---

## 2.1 The two shapes

**RAID 0** cuts data into chunks and spreads them across every member. Eight
cards, eight chunks in flight, eight times the capacity. Any one card dying
takes the whole array with it, because every file has pieces on every card.

**RAID 1** writes the same bytes to every member. Capacity of one card. Reads
can come from whichever member is free; writes must complete everywhere. It
survives losing members — seven of them, here.

The names suggest a scale. They are not on a scale; they are opposites.

## 2.2 Build the stripe

```bash
DEVS=$(python3 -c '
import sys; sys.path.insert(0, "..")
from farce import enumerate as e
print(" ".join("/dev/" + c["dev"] for c in sorted(e.discover(), key=e.key_of)))')
echo $DEVS                       # confirm eight devices before continuing

sudo mdadm --create /dev/md/lab0 --level=0 --chunk=512 \
           --raid-devices=8 --name=lab0 --metadata=1.2 --run $DEVS
```

```bash
cat /proc/mdstat
sudo mdadm --detail /dev/md/lab0
```

Read the `Chunk Size` line. 512 KB means the first 512 KB of the array live on
card 1, the next on card 2, and so on. A 4 KB read touches exactly one card. A
4 MB read touches all eight.

That sentence predicts the results below. Write down what you expect before you
measure.

## 2.3 Measure the stripe

```bash
sudo fio --name=seqread --filename=/dev/md/lab0 --rw=read --bs=1M \
         --iodepth=8 --ioengine=libaio --direct=1 \
         --runtime=30 --time_based --group_reporting

sudo fio --name=randread --filename=/dev/md/lab0 --rw=randread --bs=4k \
         --iodepth=32 --ioengine=libaio --direct=1 \
         --runtime=30 --time_based --group_reporting
```

Compare against your single card from Lab 1.

Sequential should be several times faster — not eight, and the gap is the lab.
Random 4 KiB should be **roughly the same per operation**, because a 4 KiB read
still waits on one card; what improves is how many can be in flight at once.

> **Check:** your sequential figure is well short of eight times one card.
> Name three ceilings between the card and the CPU that could account for it.
> One of them is in `docs/reference-rig.md`.

## 2.4 Tear it down and mirror instead

```bash
sudo mdadm --stop /dev/md/lab0
sudo mdadm --zero-superblock $DEVS

sudo mdadm --create /dev/md/lab1 --level=1 \
           --raid-devices=8 --name=lab1 --metadata=1.2 --run $DEVS
```

Watch it build:

```bash
watch -n2 cat /proc/mdstat
```

It has to copy one member onto seven others before it is redundant. Time it. The
number matters in Lab 3.

```bash
lsblk /dev/md/lab1
```

**Eight cards, one card of capacity.** That is the price.

## 2.5 Measure the mirror

Same two commands, `--filename=/dev/md/lab1`.

Reads should be respectable: mdadm can serve different reads from different
members. Writes are the interesting case — every write goes to all eight, so the
array is as slow as its slowest card at any moment, and MicroSD cards pause
unpredictably to do internal housekeeping.

> **Check:** run a write test on the mirror with `--allow-writes`-style caution
> (it destroys the array's contents, which is fine here). Compare mean latency
> to 99th percentile. The gap is much wider than on a single card. Why does
> mirroring *amplify* a latency outlier rather than average it away?

## 2.6 Clean up

```bash
sudo mdadm --stop /dev/md/lab1
sudo mdadm --zero-superblock $DEVS
```

---

## What you should be able to answer

1. RAID 0 across eight cards multiplied sequential bandwidth but barely moved
   4 KiB random IOPS. Explain both results with the chunk size.
2. A colleague says "we use RAID 0 for the backup server because it's fast."
   What is the specific thing that is wrong with that sentence?
3. `openfarce` uses RAID 0 for an array whose media is expected to wear out in
   about 64 days. Given lab 2, is that a defensible choice? Argue it both ways.

Question 3 has no answer key. The project made a choice; the disclaimer says
what it costs.
