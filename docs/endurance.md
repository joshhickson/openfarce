# The endurance counter: what it measures and what it guesses

The campaign page shows a live counter with two figures: days elapsed and
projected days remaining. This document exists so that anyone can check whether
that projection deserves any weight.

Short answer: the elapsed figure is measured, the remaining figure is an
estimate resting on two assumptions we cannot verify from the host, and the
error bars are wide enough to drive a bus through.

---

## Measured

**Logical bytes written per card.** Field 7 of `/sys/block/<dev>/stat` is a
count of sectors written, maintained by the kernel block layer. Multiplied by
512, that is the number of bytes the host asked the card to store.

This is a real measurement with one caveat: the counter resets when the device
is re-enumerated, which happens on reboot and on any replug. `endure.py` treats
a decrease as a reset and carries the accumulated total in its own ledger on
disk, so the record survives. It does mean a card that drops off the bus and
comes back mid-write loses the delta across that gap.

## Estimated

**Physical bytes programmed into NAND.** This is what actually wears the cells,
and it is invisible from the host. The card's controller does garbage collection
and wear levelling privately, reports nothing, and has no SMART interface.

We estimate it as `logical x WAF`, where WAF is the write amplification factor.

The default is **5.0**, the conservative figure from the Feasibility Report. The
report's own realistic figure for this workload — small, fragmented, random
writes to a consumer card with no DRAM cache and no TRIM — is **10.0 or higher**.
We publish the conservative one and label it, which means the projection is
probably optimistic by a factor of two.

If the array dies at roughly half the projected time, the WAF assumption is the
explanation, and that outcome should be read as the report having been right.

**Total endurance.** Estimated as `capacity x rated P/E cycles`. Consumer cards
are rated 1,000 to 3,000 program/erase cycles. We assume **1,000** — the
pessimistic end — because these are the cheapest cards on the market and the
rating is a marketing number rather than a guarantee.

These two assumptions pull in opposite directions, which is not a justification
for either.

## What the counter does not model

- **Wear levelling quality.** Cheap cards use dynamic wear levelling only: they
  rotate writes across free space and leave static data where it is. The portion
  of the card actually being cycled is therefore smaller than its capacity, and
  it burns through its budget faster than the whole-card arithmetic suggests.
  The projection assumes perfect global wear levelling, which no card here has.
- **RAID 0 has no redundancy.** The array dies with the *first* card, not the
  average one. The counter projects the average. Expect failure before the
  projected date, not at it.
- **Thermal derating.** A card that has been throttling has been running hot,
  and hot flash wears faster. `thermal.py` logs collapse events but the
  projection does not weight them.
- **Manufacturing variance.** Forty cards from one batch will not fail together,
  and we have no way to know the spread until they start failing.

## Why publish it at all

Because the alternative is quoting the Feasibility Report's 64-day figure
indefinitely, and that figure was computed for a 64-card, 8 TB configuration
that nobody built. The shipped array is 1.28 TB across forty cards — roughly a
sixth of the pool the report modelled. Under equal write load a smaller pool
exhausts its budget sooner, so the honest position is that we do not know what
the number is for this array, and the counter is how we find out.

Both figures appear on the site side by side so the estimate can be judged
against the elapsed reality as it accumulates. When the array dies, the gap
between projection and outcome is the interesting result.

## Reproducing it

```bash
sudo python3 -m farce.endure --status               # current state, no daemon
sudo python3 -m farce.endure --daemon --waf 10.0    # the pessimistic assumption
cat /etc/farce/endure-ledger.json                   # the raw ledger
```

The ledger is plain JSON: per card, capacity and accumulated logical bytes. Every
figure on the site derives from it by the arithmetic above, and nothing else.
