#!/usr/bin/env python3
"""
thermal.py — detect throttling without a temperature sensor.

A MicroSD card exposes no thermal telemetry. There is no SMART attribute to
read and no sensor to poll; the controller throttles privately and the only
symptom visible from the host is that the card gets slower and stays slower.

So this measures the symptom. It samples per-card throughput from kernel sector
counters during whatever load is already running, establishes a baseline from
the first few minutes, and records a "throttle event" when a card's sustained
throughput collapses below a fraction of its own baseline and stays there.

This is inference, not measurement, and it is labelled that way everywhere it
surfaces. A card that has simply been given no work looks identical to a card
that is throttling, which is why an event requires sustained low throughput
while the array as a whole is busy.

    sudo python3 -m farce.thermal --watch
    sudo python3 -m farce.thermal --report
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from farce import enumerate as farce_enum  # noqa: E402
from farce.endure import sectors_written  # noqa: E402

STATE_DIR = Path(os.environ.get("FARCE_STATE_DIR", "/etc/farce"))
THERMAL_JSON = STATE_DIR / "thermal.json"

SECTOR = 512
SAMPLE_S = 10
BASELINE_SAMPLES = 18          # ~3 minutes of history before judging anything
COLLAPSE_RATIO = 0.35          # below 35% of own baseline counts as collapsed
SUSTAIN_SAMPLES = 6            # for a full minute
ARRAY_BUSY_BYTES_S = 1 << 20   # array must be doing >1 MB/s to judge idleness

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--watch", action="store_true", help="run until stopped")
    ap.add_argument("--report", action="store_true", help="print the log and exit")
    ap.add_argument("--interval", type=int, default=SAMPLE_S)
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    if args.report:
        if THERMAL_JSON.exists():
            print(THERMAL_JSON.read_text())
        else:
            print(json.dumps({"events": [], "note": "no thermal log yet"}, indent=2))
        return 0

    if not args.watch:
        ap.error("choose --watch or --report")

    history: dict[str, deque] = defaultdict(lambda: deque(maxlen=BASELINE_SAMPLES))
    low_run: dict[str, int] = defaultdict(int)
    baseline: dict[str, float] = {}
    events: list[dict] = []
    last: dict[str, int] = {}

    print("[thermal] watching; baseline needs ~%d minutes of load"
          % (BASELINE_SAMPLES * args.interval // 60), flush=True)

    while _running:
        cards = {farce_enum.key_of(c): c for c in farce_enum.discover()}
        now = time.time()
        rates: dict[str, float] = {}

        for key, card in cards.items():
            s = sectors_written(card["dev"])
            if s is None:
                continue
            if key in last:
                delta = max(0, s - last[key])
                rates[key] = delta * SECTOR / args.interval
            last[key] = s

        array_rate = sum(rates.values())
        busy = array_rate > ARRAY_BUSY_BYTES_S

        for key, rate in rates.items():
            if busy:
                history[key].append(rate)
            if len(history[key]) >= BASELINE_SAMPLES and key not in baseline:
                ordered = sorted(history[key])
                baseline[key] = ordered[len(ordered) // 2]     # median
                continue

            if key in baseline and busy and baseline[key] > 0:
                if rate < baseline[key] * COLLAPSE_RATIO:
                    low_run[key] += 1
                    if low_run[key] == SUSTAIN_SAMPLES:
                        card = cards[key]
                        ev = {
                            "at": int(now),
                            "usb_path": card.get("usb_path"),
                            "serial": card.get("serial"),
                            "baseline_bytes_per_s": int(baseline[key]),
                            "observed_bytes_per_s": int(rate),
                            "ratio": round(rate / baseline[key], 3),
                            "inference": ("sustained throughput collapse while the "
                                          "array was busy; consistent with thermal "
                                          "throttling, not directly measured"),
                        }
                        events.append(ev)
                        print("[thermal] throttle event: %s  %.1f -> %.1f MB/s"
                              % (card.get("usb_path"),
                                 baseline[key] / 1e6, rate / 1e6), flush=True)
                else:
                    low_run[key] = 0

        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            THERMAL_JSON.write_text(json.dumps({
                "schema": "farce-thermal/1",
                "updated": int(now),
                "method": ("throughput-collapse detection; MicroSD exposes no "
                           "temperature sensor, so throttling is inferred"),
                "collapse_ratio": COLLAPSE_RATIO,
                "cards_with_baseline": len(baseline),
                "events": events,
            }, indent=2) + "\n")
        except PermissionError:
            pass

        time.sleep(args.interval)

    print("[thermal] %d event(s) recorded" % len(events))
    return 0


if __name__ == "__main__":
    sys.exit(main())
