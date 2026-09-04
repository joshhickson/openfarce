# Labs 4–8 — outlines

These are outlines, not labs. Labs 1–3 were written against commands whose
output is predictable from the documentation; these five all turn on numbers
nobody has measured on this rig yet. Writing them out in full now would mean
inventing the results, and a lab whose expected output is a guess teaches the
guess.

Each becomes a lab once the rig has run it once. Addendum A2.4.1.

---

## Lab 4 — Latency against bandwidth

**The question:** why don't eight slow devices add up to one fast one?

- Measure a single card, the 8-card stripe, and a USB SSD in the same slot, at
  1 MiB and at 4 KiB, using `python3 -m farce.bench --all --baseline`.
- Build the ratio table. Sequential scales with members; random does not.
- Introduce queue depth as the variable that separates them: at QD1 the array is
  one card, at QD32 it is eight.
- Compute the theoretical ceiling from the Pi's single VL805 controller
  (~350 MB/s, A2.1.2) and find where the measurement meets it.

**Needs first:** a `--baseline` run on real hardware, and an SSD to compare
against. The comparison is the lab; without it this is arithmetic.

---

## Lab 5 — Swap and memory pressure

**The question:** what does a computer do when it runs out of memory?

- `free -h`, then swap on the array, then `free -h` again. The kernel reports
  the array as memory, which is the entire basis for the campaign's headline.
- Run something deliberately too large. Watch `vmstat 1`: `si`/`so` columns are
  pages moving in and out.
- Contrast `vm.swappiness` at 10 and at 100 on the same workload.
- Establish the honest conclusion: swap is not more memory, it is a slower place
  to keep memory, and the machine is idle while it waits.

**Needs first:** measured page-in latency on this rig. The teaching point is a
ratio — how many CPU cycles fit inside one page fault — and the ratio has to be
real.

---

## Lab 6 — Thermal throttling

**The question:** why does the array get slower the longer you use it?

- Sustained sequential write with `farce.thermal --watch` running.
- Graph throughput against time. Expect a cliff, not a slope.
- Repeat with the fan off, then on. Repeat with one card sanded, if anyone is
  willing (`docs/reference-rig.md` has the procedure and the warnings).
- Tie back to why the enclosure is an open lattice.

**Needs first:** a throttle event actually observed. The Feasibility Report
projects the collapse from 104 MB/s to under 10; this rig either reproduces that
or it does not, and either result is worth having. If none occurs, the lab says
none occurred.

---

## Lab 7 — Wear and write amplification

**The question:** how do you measure something the device refuses to tell you?

- Read the host's own sector counters; note that the card reports nothing.
- Run `farce.endure` and read `counter.json`, including the `assumptions` block.
- The core exercise: WAF cannot be observed from the host. Discuss what would be
  needed to measure it directly, and why the counter reports measured logical
  bytes and *estimated* physical wear as separate figures.
- Optional and destructive: write to one card until it fails. This is the only
  lab in the set that reaches a real conclusion in a semester.

**Needs first:** a multi-day endurance run. Everything here depends on the
counter having a history.

---

## Lab 8 — A language model as the workload

**The question:** what happens when the working set is bigger than the machine?

- `serve.sh --profile demo-fits` with a model that fits in RAM. Record tok/s.
- `serve.sh --profile demo-swaps` with one that does not. Record tok/s and
  seconds per token.
- The ratio between them is the whole point, and it is expected to be brutal.
- Compare against the Feasibility Report's projection for the 40-lane array and
  discuss what does and does not transfer between eight lanes and forty.

**Needs first:** both runs, on hardware. The projected figures in A2.2.1 are
estimates by the person who wrote the addendum, not measurements, and a lab
built on them would be teaching someone's arithmetic as a result.

---

## Why these are outlines

The rule that governs the rest of this project applies here: a number that has
not been measured is labelled as a projection, and something presented as a
result has to be one. Labs 1–3 are complete because their outputs follow from
documented behaviour. Labs 4–8 are the ones with interesting numbers in them,
which is exactly why they have to wait for the numbers.
