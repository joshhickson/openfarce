#!/usr/bin/env python3
"""
publish_counter.py — push the endurance counter to the site.

The site reads a static JSON file. This copies the daemon's counter.json into
the site repository, commits, and pushes. Run it hourly from a timer.

Refuses to publish in three cases, each of which would put a wrong number on a
public page:

  * the counter is missing or malformed
  * the counter is older than --max-age (default 3 hours), which means the
    daemon has stopped and the figure is stale
  * --require-real is set and the ledger came from a simulated rig

On a stale counter it does not blank the page. The site keeps the last good
value and its timestamp, because a number with an honest date on it is more
useful to a reader than an error.

    python3 tools/publish_counter.py --site ~/src/joshhickson.github.io
    python3 tools/publish_counter.py --site DIR --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("FARCE_STATE_DIR", "/etc/farce"))
COUNTER_JSON = STATE_DIR / "counter.json"
SITE_REL = Path("solutions/farce-flash/data/counter.json")


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--site", required=True, help="path to the site repository")
    ap.add_argument("--source", default=str(COUNTER_JSON))
    ap.add_argument("--max-age", type=int, default=3 * 3600,
                    help="refuse to publish a counter older than this (seconds)")
    ap.add_argument("--require-real", action="store_true",
                    help="refuse to publish a counter from a simulated rig")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.source)
    site = Path(args.site).expanduser()
    dest = site / SITE_REL

    if not src.exists():
        print("no counter at %s; is farce-endure running?" % src, file=sys.stderr)
        return 1
    try:
        payload = json.loads(src.read_text())
    except ValueError as exc:
        print("counter is not valid JSON: %s" % exc, file=sys.stderr)
        return 1

    for field in ("state", "updated", "days_elapsed"):
        if field not in payload:
            print("counter is missing %r; refusing to publish" % field, file=sys.stderr)
            return 1

    age = time.time() - payload["updated"]
    if age > args.max_age:
        print("counter is %.1f hours old; refusing to publish a stale figure."
              % (age / 3600.0), file=sys.stderr)
        print("The site keeps its last good value and timestamp.", file=sys.stderr)
        return 1

    if args.require_real and payload.get("simulated"):
        print("counter came from a simulated rig; refusing", file=sys.stderr)
        return 1

    if not dest.parent.is_dir():
        print("no such directory: %s (is --site right?)" % dest.parent, file=sys.stderr)
        return 1

    new = json.dumps(payload, indent=1) + "\n"
    if dest.exists() and dest.read_text() == new:
        print("counter unchanged; nothing to publish")
        return 0

    if args.dry_run:
        print("would write %s:\n%s" % (dest, new))
        return 0

    dest.write_text(new)

    rc, out = run(["git", "add", str(SITE_REL)], site)
    if rc:
        print(out, file=sys.stderr)
        return 1
    rc, out = run(["git", "commit", "-m",
                   "Endurance counter: day %s" % payload["days_elapsed"]], site)
    if rc and "nothing to commit" not in out:
        print(out, file=sys.stderr)
        return 1
    rc, out = run(["git", "push"], site)
    if rc:
        print("push failed: %s" % out, file=sys.stderr)
        return 1

    print("published day %s, %s days projected remaining"
          % (payload["days_elapsed"], payload.get("projected_days_remaining")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
