#!/usr/bin/env python3
"""
endure.py — measure how fast the array is destroying itself.

Runs a continuous write load and accounts for the damage. Writes counter.json,
which the campaign site reads.

WHAT IS MEASURED AND WHAT IS ESTIMATED
--------------------------------------
Measured, from /sys/block/<dev>/stat sector counters:
    logical bytes written to each card since this daemon started.

Estimated, and clearly labelled as such:
    physical bytes actually programmed into NAND, which is the logical figure
    multiplied by a write amplification factor we cannot observe from the host.
    The card's controller does garbage collection privately and reports nothing.

    WAF default is 5.0, the conservative figure from the Feasibility Report.
    The report's own realistic figure is 10.0 or higher for fragmented writes on
    a consumer card with no DRAM cache and no TRIM. If the array dies at half
    the projected time, the WAF assumption is the first thing to suspect.

Also estimated:
    total endurance, as capacity x rated P/E cycles. Consumer cards are rated
    1,000 to 3,000 cycles; we assume 1,000, the pessimistic end, because these
    are the cheapest cards on the market and the rating is a marketing number.

The projection is therefore an estimate resting on two numbers we cannot verify
and one we can. It is published with the assumptions attached, and both the
elapsed and remaining figures appear on the site so the estimate can be judged
against the elapsed reality as it accumulates.

    sudo python3 -m farce.endure --daemon         # run continuously
    sudo python3 -m farce.endure --status         # print and exit
    sudo python3 -m farce.endure --daemon --waf 10.0
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from farce import enumerate as farce_enum  # noqa: E402

STATE_DIR = Path(os.environ.get("FARCE_STATE_DIR", "/etc/farce"))
COUNTER_JSON = STATE_DIR / "counter.json"
LEDGER_JSON = STATE_DIR / "endure-ledger.json"

SECTOR = 512
DEFAULT_WAF = 5.0
DEFAULT_PE_CYCLES = 1000
SAMPLE_INTERVAL = 60

_running = True


def _stop(signum, frame):
    global _running
    _running = False
    print("\n[endure] stopping; ledger is on disk and will resume", flush=True)


def sectors_written(dev: str) -> int | None:
    """Field 7 of /sys/block/<dev>/stat is sectors written."""
    try:
        fields = Path("/sys/block/%s/stat" % dev).read_text().split()
        return int(fields[6])
    except (OSError, IndexError, ValueError):
        return None


def snapshot() -> dict[str, dict]:
    out = {}
    for card in farce_enum.discover():
        s = sectors_written(card["dev"])
        if s is None:
            continue
        out[farce_enum.key_of(card)] = {
            "dev": card["dev"],
            "usb_path": card.get("usb_path"),
            "serial": card.get("serial"),
            "bytes_capacity": card["bytes"],
            "sectors_written": s,
        }
    return out


def load_ledger() -> dict:
    if LEDGER_JSON.exists():
        try:
            return json.loads(LEDGER_JSON.read_text())
        except (OSError, ValueError):
            pass
    return {"started": None, "cards": {}, "throttle_events": 0}


def save_ledger(ledger: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_JSON.write_text(json.dumps(ledger, indent=2) + "\n")


def project(ledger: dict, waf: float, pe_cycles: int) -> dict:
    """Turn the ledger into a projection, with the assumptions attached."""
    now = time.time()
    started = ledger.get("started") or now
    elapsed_s = max(1.0, now - started)

    logical = sum(c.get("logical_bytes", 0) for c in ledger["cards"].values())
    capacity = sum(c.get("bytes_capacity", 0) for c in ledger["cards"].values())

    physical = logical * waf
    endurance_bytes = capacity * pe_cycles
    rate = physical / elapsed_s                       # bytes of wear per second

    if rate > 0 and endurance_bytes > 0:
        remaining_s = max(0.0, (endurance_bytes - physical) / rate)
        remaining_days = remaining_s / 86400.0
    else:
        remaining_days = None

    # "live" means a real rig has actually written something. An empty ledger
    # must not publish as live: the site would render a counter of zeroes as
    # though it were a measurement.
    measuring = bool(ledger["cards"]) and logical > 0

    return {
        "schema": "farce-counter/1",
        "state": "live" if measuring else "pending",
        "note": (None if measuring else
                 "No writes recorded yet. The rig is not running, or has not "
                 "been given any load."),
        "updated": int(now),
        "days_elapsed": round(elapsed_s / 86400.0, 2),
        "projected_days_remaining": (round(remaining_days, 1)
                                     if remaining_days is not None else None),
        "cards_present": len(ledger["cards"]),
        "logical_tb_written": round(logical / 1e12, 4),
        "estimated_physical_tb_written": round(physical / 1e12, 4),
        "array_capacity_tb": round(capacity / 1e12, 4),
        "throttle_events": ledger.get("throttle_events", 0),
        "assumptions": {
            "waf": waf,
            "waf_note": ("Write amplification cannot be observed from the host. "
                         "5.0 is the Feasibility Report's conservative figure; "
                         "its realistic figure for this write pattern is 10.0 "
                         "or higher."),
            "pe_cycles": pe_cycles,
            "pe_note": ("Rated program/erase cycles per cell, assumed at the "
                        "pessimistic end of the 1,000-3,000 consumer range."),
            "measured": "logical bytes written, from kernel sector counters",
            "estimated": "physical wear, total endurance, days remaining",
        },
    }


def write_counter(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    COUNTER_JSON.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--daemon", action="store_true", help="run until stopped")
    ap.add_argument("--status", action="store_true", help="print current state and exit")
    ap.add_argument("--waf", type=float, default=DEFAULT_WAF)
    ap.add_argument("--pe-cycles", type=int, default=DEFAULT_PE_CYCLES)
    ap.add_argument("--interval", type=int, default=SAMPLE_INTERVAL)
    ap.add_argument("--reset", action="store_true", help="discard the ledger and restart")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    ledger = {"started": None, "cards": {}, "throttle_events": 0} if args.reset \
        else load_ledger()

    if args.status:
        payload = project(ledger, args.waf, args.pe_cycles)
        print(json.dumps(payload, indent=2))
        return 0

    base = snapshot()
    if not base:
        print("no readers with media found; nothing to measure", file=sys.stderr)
        return 1

    if ledger["started"] is None:
        ledger["started"] = time.time()
        print("[endure] starting a new ledger at %s"
              % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)

    # Reconcile against the ledger. A card that was replaced starts from zero;
    # its accumulated wear stays on the record under its old key.
    for key, snap in base.items():
        entry = ledger["cards"].setdefault(key, {
            "dev": snap["dev"], "usb_path": snap["usb_path"],
            "serial": snap["serial"], "bytes_capacity": snap["bytes_capacity"],
            "logical_bytes": 0, "last_sectors": snap["sectors_written"],
        })
        # Counters reset on reboot or replug; treat a decrease as a reset.
        if snap["sectors_written"] < entry["last_sectors"]:
            entry["last_sectors"] = 0
        entry["dev"] = snap["dev"]
    save_ledger(ledger)

    if not args.daemon:
        write_counter(project(ledger, args.waf, args.pe_cycles))
        print("wrote %s" % COUNTER_JSON)
        return 0

    print("[endure] sampling every %ds; WAF %.1f; %d P/E cycles assumed"
          % (args.interval, args.waf, args.pe_cycles), flush=True)

    while _running:
        time.sleep(min(args.interval, 5))
        if not _running:
            break
        now = snapshot()
        for key, snap in now.items():
            entry = ledger["cards"].get(key)
            if entry is None:
                continue
            delta = snap["sectors_written"] - entry["last_sectors"]
            if delta < 0:                     # counter reset
                delta = snap["sectors_written"]
            entry["logical_bytes"] += delta * SECTOR
            entry["last_sectors"] = snap["sectors_written"]

        missing = set(ledger["cards"]) - set(now)
        if missing:
            print("[endure] %d card(s) not responding: %s"
                  % (len(missing), ", ".join(sorted(missing))), flush=True)

        payload = project(ledger, args.waf, args.pe_cycles)
        payload["cards_missing"] = sorted(missing)
        save_ledger(ledger)
        write_counter(payload)

    write_counter(project(ledger, args.waf, args.pe_cycles))
    save_ledger(ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
