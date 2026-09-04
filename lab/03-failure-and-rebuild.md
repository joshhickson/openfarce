# Lab 3 — Failure and rebuild

**About 90 minutes**, most of it waiting for a rebuild. Labs 1 and 2 first.

You are going to pull a card out of a running array, on purpose, twice: once
from a configuration that survives it and once from one that does not. This is
the lab the rig exists for. A card costs a few dollars, so you can afford to
break it in front of a class; a server's disk array cannot be destroyed as a
teaching aid.

**Everything on the cards is destroyed in this lab.**

---

## 3.1 Build something that can survive

RAID 5 stripes data across members and keeps parity, so it survives losing one.
Eight cards give you seven cards of capacity and one card of redundancy.

```bash
DEVS=$(python3 -c '
import sys; sys.path.insert(0, "..")
from farce import enumerate as e
print(" ".join("/dev/" + c["dev"] for c in sorted(e.discover(), key=e.key_of)))')

sudo mdadm --create /dev/md/lab5 --level=5 --chunk=512 \
           --raid-devices=8 --name=lab5 --metadata=1.2 --run $DEVS
watch -n2 cat /proc/mdstat        # wait for it to finish building
```

Put a filesystem and a known payload on it:

```bash
sudo mkfs.ext4 -F /dev/md/lab5
sudo mkdir -p /mnt/lab3 && sudo mount /dev/md/lab5 /mnt/lab3
sudo dd if=/dev/urandom of=/mnt/lab3/payload bs=1M count=512 status=progress
sudo sha256sum /mnt/lab3/payload | sudo tee /mnt/lab3/payload.sha256
sync
```

Keep that hash where you can see it.

## 3.2 Pull a card while it is working

Start a read in one terminal:

```bash
while true; do sudo dd if=/mnt/lab3/payload of=/dev/null bs=1M status=none; done
```

In another, watch:

```bash
watch -n1 'cat /proc/mdstat; echo; dmesg | tail -5'
```

Now **physically pull one reader out of the hub.**

Watch what happens. The kernel logs I/O errors, mdadm marks the member failed,
and — this is the point — **the reads keep working.** The array is degraded, not
dead. It is reconstructing the missing card's data from parity on every read,
which is why it is now slower.

```bash
sudo mdadm --detail /dev/md/lab5 | head -20
sha256sum /mnt/lab3/payload      # compare to the hash you kept
```

The hash still matches. Nothing was lost.

> **Check:** the array is running with no redundancy left. What happens to your
> data if a second card fails right now, and how would you know that risk exists
> if you were not standing next to the machine?

## 3.3 Rebuild it

Plug the reader back in.

```bash
sudo mdadm --detail /dev/md/lab5 | grep -E 'State|Devices'
sudo mdadm --manage /dev/md/lab5 --re-add /dev/sdX   # the returned device
```

If `--re-add` is refused, the superblock is stale; add it as a fresh spare:

```bash
sudo mdadm --zero-superblock /dev/sdX
sudo mdadm --manage /dev/md/lab5 --add /dev/sdX
```

```bash
watch -n2 cat /proc/mdstat
```

**Time the rebuild.** Then answer: during a rebuild the array reads *every*
block on *every* surviving card. On media rated for a thousand write cycles and
already worn, what does that do to the chance of a second failure?

That question is why RAID 5 fell out of favour on large drives, and this rig
demonstrates it at a scale you can watch finish.

## 3.4 Now do it to a stripe

```bash
sudo umount /mnt/lab3
sudo mdadm --stop /dev/md/lab5
sudo mdadm --zero-superblock $DEVS

sudo mdadm --create /dev/md/lab0 --level=0 --chunk=512 \
           --raid-devices=8 --name=lab0 --metadata=1.2 --run $DEVS
sudo mkfs.ext4 -F /dev/md/lab0
sudo mount /dev/md/lab0 /mnt/lab3
sudo dd if=/dev/urandom of=/mnt/lab3/payload bs=1M count=512 status=progress
sync
```

Pull a card.

```bash
cat /proc/mdstat
ls /mnt/lab3
dmesg | tail -20
```

The array is gone. Not degraded — gone. There is no parity and no mirror, so
seven eighths of every file is still on the cards and is of no use to anyone.

Plug the card back in. It does not come back:

```bash
sudo mdadm --stop /dev/md/lab0 2>&1 || true
```

> **Check:** the data is *physically still there* on seven of eight cards. Why
> can it not be recovered by any ordinary means, and what would you need to know
> to reconstruct even one file by hand?

## 3.5 Clean up

```bash
sudo umount /mnt/lab3 2>/dev/null || true
sudo mdadm --stop /dev/md/lab0 2>/dev/null || true
sudo mdadm --zero-superblock $DEVS 2>/dev/null || true
```

---

## What you should be able to answer

1. RAID 5 survived a pull and RAID 0 did not. State the cost of that survival in
   both capacity and write performance.
2. You timed a rebuild. Extrapolate: eight 16 GB cards took *t*. How long for
   eight 1 TB drives, and what does that imply about RAID 5 on modern disks?
3. `openfarce` runs RAID 0 across forty cards whose expected life is about 64
   days. Compute the probability that at least one of forty cards fails in a
   period, if each has an independent 1% chance. Then say whether "independent"
   is a fair assumption for forty identical cards bought in one batch and
   written to identically.

Question 3 is the one worth arguing about.
