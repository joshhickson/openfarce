#!/usr/bin/env bash
#
# dry_run.sh — exercise the whole pipeline on loop devices, with no hardware.
# Addendum A2.10, first item.
#
# Eight files pretending to be eight cards. The RAID is real, the swap is real,
# the bench is real; only the media is fake. This is how the assemble → bench →
# endure → counter path gets tested before any parts are bought, and it is how
# it stays tested afterwards.
#
# What it does NOT prove: anything about MicroSD cards. Loop devices on an SSD
# are fast, reliable and do not wear out, which is the opposite of the thing
# this project is about. It proves the plumbing, nothing else. Every number it
# produces is discarded.
#
#   sudo ./tools/dry_run.sh              # run, then clean up
#   sudo ./tools/dry_run.sh --keep       # leave the array up for poking at
#
# Requires: mdadm, fio, python3. On Debian/Ubuntu/WSL:
#   sudo apt-get install -y mdadm fio
set -euo pipefail

KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

LANES="${FARCE_LANES:-8}"
IMG_MB="${DRY_RUN_IMG_MB:-256}"
WORK="${DRY_RUN_DIR:-/tmp/farce-dry-run}"
MD_DEV="/dev/md/farce-dry"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log()  { printf '[dry-run] %s\n' "$*"; }
die()  { printf '[dry-run] FATAL: %s\n' "$*" >&2; exit 1; }
step() { printf '\n[dry-run] === %s ===\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "must run as root (loop devices and mdadm need it)"
for c in losetup mdadm mkswap swapon python3; do
  command -v "$c" >/dev/null 2>&1 || die "missing: $c  (apt-get install mdadm)"
done

LOOPS=()

cleanup() {
  [ "$KEEP" -eq 1 ] && { log "--keep: leaving $MD_DEV up. Clean up with:"; \
                         log "  swapoff $MD_DEV; mdadm --stop $MD_DEV; losetup -D; rm -rf $WORK"; \
                         return; }
  step "cleaning up"
  swapoff "$MD_DEV" 2>/dev/null || true
  mdadm --stop "$MD_DEV" 2>/dev/null || true
  for l in "${LOOPS[@]:-}"; do [ -n "$l" ] && losetup -d "$l" 2>/dev/null || true; done
  rm -rf "$WORK"
  log "done"
}
trap cleanup EXIT

# ------------------------------------------------------------------ backing ---

step "creating $LANES backing files of ${IMG_MB} MB in $WORK"
mkdir -p "$WORK"
for i in $(seq 1 "$LANES"); do
  f="$WORK/card${i}.img"
  truncate -s "${IMG_MB}M" "$f"
  l="$(losetup --find --show "$f")"
  LOOPS+=("$l")
  printf '[dry-run]   card%-2d %s -> %s\n' "$i" "$f" "$l"
done

# --------------------------------------------------------------------- raid ---

step "creating RAID 0 across ${#LOOPS[@]} loop devices"
mdadm --create "$MD_DEV" --level=0 --chunk=512 \
      --raid-devices="${#LOOPS[@]}" --name=farce-dry --metadata=1.2 \
      --run "${LOOPS[@]}"
udevadm settle 2>/dev/null || sleep 1
lsblk -o NAME,SIZE,TYPE "$MD_DEV" | sed 's/^/[dry-run]   /'

step "making it swap and enabling it"
mkswap -L farce-dry "$MD_DEV" >/dev/null
swapon --priority 1 "$MD_DEV"
swapon --show | sed 's/^/[dry-run]   /'

# ------------------------------------------------------------------- python ---

export FARCE_STATE_DIR="$WORK/state"
export FARCE_LANES="$LANES"
export FARCE_CARD_BYTES=$(( IMG_MB * 1024 * 1024 ))
export FARCE_RIG_NAME="dry run (loop devices, not hardware)"
export PYTHONPATH="$ROOT"
mkdir -p "$FARCE_STATE_DIR"

step "rig identity that every artifact will carry"
python3 -m farce.rig | sed 's/^/[dry-run]   /'

step "bench.py against the array"
if command -v fio >/dev/null 2>&1; then
  python3 -m farce.bench --array --runtime 5 --size 64M \
          -o "$FARCE_STATE_DIR/bench.json" | sed 's/^/[dry-run]   /'
  python3 - <<'PY' | sed 's/^/[dry-run]   /'
import json, os
b = json.load(open(os.environ["FARCE_STATE_DIR"] + "/bench.json"))
print("bench.json rig block:", json.dumps(b.get("rig", {}), indent=2)[:400])
assert b.get("rig", {}).get("lanes"), "bench.json has no rig stamp"
print("OK: bench.json carries its lane count")
PY
else
  log "fio not installed; skipping bench (apt-get install fio)"
fi

step "endure.py, one sample"
python3 -m farce.endure --status | sed 's/^/[dry-run]   /' || true

step "counter payload"
python3 - <<'PY' | sed 's/^/[dry-run]   /'
import json, os, pathlib
p = pathlib.Path(os.environ["FARCE_STATE_DIR"]) / "counter.json"
if not p.exists():
    print("no counter.json yet; endure --daemon writes it")
else:
    c = json.loads(p.read_text())
    print("state:", c.get("state"))
    assert "rig" in c, "counter.json has no rig stamp"
    print("lanes:", c["rig"]["lanes"], "|", c["rig"]["caveat"][:70], "...")
    print("OK: counter.json carries its lane count")
PY

step "PASS — the plumbing works on loop devices"
log "Nothing above says anything about MicroSD cards. It says the RAID,"
log "the swap, the bench and the counter paths run end to end."
