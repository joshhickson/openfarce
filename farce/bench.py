#!/usr/bin/env python3
"""
bench.py — measure the array, per card and in aggregate.

Wraps fio. Produces JSON that the campaign site reads directly, so no number on
the site is ever typed by hand.

Four profiles, chosen because they are the four that decide whether the
architecture works at all:

  seqread   sequential read, 1 MiB blocks, queue depth 8
            The optimistic number. Marketing arithmetic (cards x per-card
            ceiling) predicts this one and it is the only one it predicts well.

  seqwrite  sequential write, 1 MiB blocks, queue depth 8
            What KV cache offload actually does, if the write path is behaving.

  randread  4 KiB random read, queue depth 32
            The number that kills it. MicroSD controllers have a command queue
            one to four entries deep and no DRAM cache. Expect two to three
            orders of magnitude below NVMe.

  randwrite 4 KiB random write, queue depth 32
            Worst case. Drives write amplification, which drives the endurance
            projection in endure.py.

    sudo python3 -m farce.bench --array            # the assembled array
    sudo python3 -m farce.bench --per-card         # every card individually
    sudo python3 -m farce.bench --all -o bench.json
    python3 -m farce.bench --dry-run               # show the fio commands only

Reads are safe. WRITES ARE DESTRUCTIVE and are refused unless --allow-writes is
given, because a stray run against the wrong device destroys a filesystem.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from farce import enumerate as farce_enum  # noqa: E402

MD_DEV = os.environ.get("FARCE_MD_DEV", "/dev/md/farce0")
STATE_DIR = Path(os.environ.get("FARCE_STATE_DIR", "/etc/farce"))

PROFILES = {
    "seqread":   dict(rw="read",      bs="1M",  iodepth=8,  destructive=False),
    "seqwrite":  dict(rw="write",     bs="1M",  iodepth=8,  destructive=True),
    "randread":  dict(rw="randread",  bs="4k",  iodepth=32, destructive=False),
    "randwrite": dict(rw="randwrite", bs="4k",  iodepth=32, destructive=True),
}


def fio_cmd(target: str, profile: str, runtime: int, size: str) -> list[str]:
    p = PROFILES[profile]
    return [
        "fio",
        "--name=%s" % profile,
        "--filename=%s" % target,
        "--rw=%s" % p["rw"],
        "--bs=%s" % p["bs"],
        "--iodepth=%d" % p["iodepth"],
        "--ioengine=libaio",
        "--direct=1",
        "--runtime=%d" % runtime,
        "--time_based",
        "--size=%s" % size,
        "--group_reporting",
        "--output-format=json",
    ]


def run_fio(target: str, profile: str, runtime: int, size: str,
            dry_run: bool = False) -> dict | None:
    cmd = fio_cmd(target, profile, runtime, size)
    if dry_run:
        print("  " + " ".join(cmd))
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=runtime + 120, check=True).stdout
    except FileNotFoundError:
        raise SystemExit("fio is not installed:  sudo apt install fio")
    except subprocess.CalledProcessError as exc:
        print("  fio failed on %s/%s: %s" % (target, profile,
                                             (exc.stderr or "").strip()[:200]),
              file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("  fio timed out on %s/%s" % (target, profile), file=sys.stderr)
        return None

    data = json.loads(out)
    job = data["jobs"][0]
    side = "read" if "read" in PROFILES[profile]["rw"] else "write"
    stats = job[side]
    return {
        "bw_bytes_per_s": stats["bw_bytes"],
        "iops": round(stats["iops"], 1),
        "lat_mean_us": round(stats["lat_ns"]["mean"] / 1000.0, 1),
        "lat_p99_us": round(
            stats["clat_ns"].get("percentile", {}).get("99.000000", 0) / 1000.0, 1),
    }


def bench_target(target: str, profiles: list[str], runtime: int, size: str,
                 allow_writes: bool, dry_run: bool) -> dict:
    result = {}
    for profile in profiles:
        if PROFILES[profile]["destructive"] and not allow_writes:
            result[profile] = {"skipped": "destructive; pass --allow-writes"}
            continue
        print("  %-10s %s" % (profile, target))
        r = run_fio(target, profile, runtime, size, dry_run)
        if r:
            result[profile] = r
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--array", action="store_true", help="benchmark the assembled array")
    ap.add_argument("--per-card", action="store_true", help="benchmark each card alone")
    ap.add_argument("--all", action="store_true", help="both")
    ap.add_argument("--allow-writes", action="store_true",
                    help="enable the destructive write profiles")
    ap.add_argument("--runtime", type=int, default=30, help="seconds per profile")
    ap.add_argument("--size", default="4G", help="fio --size")
    ap.add_argument("--dry-run", action="store_true", help="print fio commands only")
    ap.add_argument("-o", "--output", default=None, help="write JSON here")
    args = ap.parse_args()

    if not (args.array or args.per_card or args.all):
        ap.error("choose --array, --per-card or --all")
    if not args.dry_run and not shutil.which("fio"):
        raise SystemExit("fio is not installed:  sudo apt install fio")

    profiles = list(PROFILES)
    report: dict = {
        "schema": "farce-bench/1",
        "started": int(time.time()),
        "runtime_s": args.runtime,
        "writes_enabled": args.allow_writes,
        "array": None,
        "cards": {},
        "aggregate": {},
    }

    if args.array or args.all:
        if not Path(MD_DEV).exists() and not args.dry_run:
            print("no array at %s; run assemble.sh first" % MD_DEV, file=sys.stderr)
        else:
            print("array: %s" % MD_DEV)
            report["array"] = bench_target(MD_DEV, profiles, args.runtime,
                                           args.size, args.allow_writes,
                                           args.dry_run)

    if args.per_card or args.all:
        cards = farce_enum.discover()
        print("per-card: %d reader(s)" % len(cards))
        for card in sorted(cards, key=farce_enum.key_of):
            key = farce_enum.key_of(card)
            report["cards"][key] = bench_target(
                "/dev/" + card["dev"], profiles, max(10, args.runtime // 3),
                "1G", args.allow_writes, args.dry_run)

        # Sum of the parts, for comparison against the measured whole. The gap
        # between these two is the cost of the host interface, and it is the
        # number the architecture lives or dies on.
        for profile in profiles:
            vals = [c[profile]["bw_bytes_per_s"]
                    for c in report["cards"].values()
                    if profile in c and "bw_bytes_per_s" in c[profile]]
            if vals:
                report["aggregate"][profile] = {
                    "sum_of_cards_bytes_per_s": sum(vals),
                    "cards_measured": len(vals),
                }
                if report["array"] and profile in report["array"]:
                    measured = report["array"][profile].get("bw_bytes_per_s")
                    if measured:
                        report["aggregate"][profile]["array_bytes_per_s"] = measured
                        report["aggregate"][profile]["scaling_efficiency"] = round(
                            measured / sum(vals), 3)

    report["finished"] = int(time.time())

    if args.dry_run:
        return 0

    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
        print("wrote %s" % args.output)
    else:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / "bench.json").write_text(text)
            print("wrote %s" % (STATE_DIR / "bench.json"))
        except PermissionError:
            print(text)

    if report["array"]:
        for profile in profiles:
            r = report["array"].get(profile, {})
            if "bw_bytes_per_s" in r:
                print("%-10s %8.2f MB/s  %9.0f IOPS  p99 %.1f ms"
                      % (profile, r["bw_bytes_per_s"] / 1e6, r["iops"],
                         r["lat_p99_us"] / 1000.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
