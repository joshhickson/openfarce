#!/usr/bin/env python3
"""
enumerate.py — find every card reader and give it a stable name.

Kernel device names (/dev/sda, /dev/sdb, ...) are assigned in the order devices
happen to enumerate, which changes on every boot and every time a hub comes up
in a different order. Nothing in this project may depend on them.

Instead each reader is identified by the pair

    (usb_path, lun, serial)

where usb_path is the physical topology — which port on which hub on which
controller — and serial is whatever the reader reports. Either alone is
insufficient: cheap readers frequently share a serial across units, and a reader
moved to a different port changes its path. Together they are stable enough to
detect a missing slot and say which one.

Writes /etc/farce/cards.json (override with FARCE_STATE_DIR).

    sudo python3 -m farce.enumerate            # write the map
    python3 -m farce.enumerate --check         # compare against the saved map
    python3 -m farce.enumerate --expect 40     # fail unless 40 are present
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STATE_DIR = Path(os.environ.get("FARCE_STATE_DIR", "/etc/farce"))
CARDS_JSON = STATE_DIR / "cards.json"

SYS_BLOCK = Path("/sys/block")


def _udev(dev: str) -> dict[str, str]:
    """udevadm properties for a block device, as a dict."""
    try:
        out = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name=/dev/{dev}"],
            capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    props = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        if key:
            props[key] = value
    return props


def _usb_path(dev: str) -> str | None:
    """Physical topology of a block device, e.g. '2-1.4.3:1.0'.

    Read from the sysfs symlink rather than udev, because it survives a reader
    that reports no serial at all.
    """
    try:
        real = (SYS_BLOCK / dev).resolve()
    except OSError:
        return None
    # .../usb2/2-1/2-1.4/2-1.4.3/2-1.4.3:1.0/host6/.../block/sdc
    for part in reversed(real.parts):
        if re.fullmatch(r"\d+-[\d.]+:\d+\.\d+", part):
            return part
    return None


def _scsi_addr(dev: str) -> str | None:
    """SCSI address of a block device, e.g. '6:0:0:3' (host:channel:target:lun).

    A multi-LUN card reader — the way essentially every commercial multi-slot
    reader is built — puts all of its slots behind ONE USB interface. They share
    a usb_path and differ only by the LUN at the end of this address, so without
    it every card in such a reader has the same identity and the tools cannot
    tell slot 1 from slot 5.

    Eight separate readers on a hub do not need this; a GL3223-class reader
    cannot work without it.
    """
    try:
        real = (SYS_BLOCK / dev).resolve()
    except OSError:
        return None
    # .../2-1.4.3:1.0/host6/target6:0:0/6:0:0:3/block/sde
    for part in reversed(real.parts):
        if re.fullmatch(r"\d+:\d+:\d+:\d+", part):
            return part
    return None


def discover() -> list[dict]:
    """Every removable USB block device currently attached."""
    cards = []
    if not SYS_BLOCK.is_dir():
        return cards

    for entry in sorted(SYS_BLOCK.iterdir()):
        dev = entry.name
        if not re.fullmatch(r"sd[a-z]+|mmcblk\d+", dev):
            continue

        props = _udev(dev)
        if props.get("ID_BUS") not in ("usb", None):
            continue
        if props.get("ID_BUS") is None and not dev.startswith("mmcblk"):
            continue

        removable = (entry / "removable").read_text().strip() == "1" \
            if (entry / "removable").exists() else False
        try:
            sectors = int((entry / "size").read_text().strip())
        except (OSError, ValueError):
            sectors = 0

        if sectors == 0:          # reader present, no card in it
            continue

        cards.append({
            "dev": dev,
            "usb_path": _usb_path(dev),
            "scsi_addr": _scsi_addr(dev),
            "serial": props.get("ID_SERIAL_SHORT") or props.get("ID_SERIAL") or "",
            "model": props.get("ID_MODEL", "").replace("_", " ").strip(),
            "vendor": props.get("ID_VENDOR", "").replace("_", " ").strip(),
            "bytes": sectors * 512,
            "removable": removable,
        })
    return cards


def key_of(card: dict) -> str:
    """Stable identity. Never the kernel name.

    Three parts, because no two of them are sufficient:
      usb_path   which port on which hub — but shared by every slot of a
                 multi-LUN reader
      scsi_addr  the LUN, which separates those slots — but its host number
                 is assigned in probe order and is not stable across boots
      serial     often identical across cheap readers from one batch

    Together they identify a slot on any of the reader topologies this project
    uses. Only the LUN field of scsi_addr is stable, so that is the part used.
    """
    lun = (card.get("scsi_addr") or "").rsplit(":", 1)[-1] or "nolun"
    return "%s|%s|%s" % (card.get("usb_path") or "nopath",
                         lun,
                         card.get("serial") or "noserial")


def duplicate_serials(cards: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in cards:
        s = c.get("serial") or ""
        if s:
            counts[s] = counts.get(s, 0) + 1
    return {s: n for s, n in counts.items() if n > 1}


def save(cards: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(cards),
        "total_bytes": sum(c["bytes"] for c in cards),
        "cards": {key_of(c): c for c in sorted(cards, key=key_of)},
    }
    CARDS_JSON.write_text(json.dumps(payload, indent=2) + "\n")


def load() -> dict:
    if not CARDS_JSON.exists():
        return {}
    return json.loads(CARDS_JSON.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--check", action="store_true",
                    help="compare the current devices against the saved map")
    ap.add_argument("--expect", type=int, default=None,
                    help="exit non-zero unless exactly this many readers are present")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    cards = discover()

    dupes = duplicate_serials(cards)
    if dupes:
        print("warning: %d serial(s) reported by more than one reader — %s"
              % (len(dupes), ", ".join(sorted(dupes))), file=sys.stderr)
        print("         identity falls back to USB path alone for those readers; "
              "do not move them between ports.", file=sys.stderr)

    if args.check:
        saved = load()
        if not saved:
            print("no saved map at %s; run without --check first" % CARDS_JSON,
                  file=sys.stderr)
            return 2
        now = {key_of(c) for c in cards}
        before = set(saved.get("cards", {}))
        missing = sorted(before - now)
        added = sorted(now - before)
        for k in missing:
            c = saved["cards"][k]
            print("MISSING  usb_path=%s serial=%s (was %s)"
                  % (c.get("usb_path"), c.get("serial"), c.get("dev")))
        for k in added:
            print("NEW      %s" % k)
        if not missing and not added:
            print("all %d readers present" % len(cards))
        return 1 if missing else 0

    if args.json:
        json.dump({"count": len(cards), "cards": cards}, sys.stdout, indent=2)
        print()
    else:
        for c in sorted(cards, key=key_of):
            print("%-10s %-18s %-20s %8.1f GB  %s"
                  % (c["dev"], c.get("usb_path") or "-", c.get("serial") or "-",
                     c["bytes"] / 1e9, c.get("model") or ""))
        print("\n%d reader(s) with media" % len(cards))

    if os.access(STATE_DIR.parent, os.W_OK) or STATE_DIR.exists():
        try:
            save(cards)
            print("wrote %s" % CARDS_JSON, file=sys.stderr)
        except PermissionError:
            print("not writing %s (need root)" % CARDS_JSON, file=sys.stderr)

    if args.expect is not None and len(cards) != args.expect:
        print("expected %d readers, found %d" % (args.expect, len(cards)),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
