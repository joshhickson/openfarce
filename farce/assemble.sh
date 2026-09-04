#!/usr/bin/env bash
#
# assemble.sh — bring the array up from cold boot.
#
# Order of operations matters and is not negotiable:
#
#   1. Stage the power-up. Forty readers spinning up at once pulls more current
#      than a hub's supply can deliver, and the failure mode is not a clean
#      error: readers enumerate, then drop off the bus half a second later, and
#      you spend a week thinking you have a driver problem. Eight at a time,
#      two seconds apart, if uhubctl is available to gate the ports.
#   2. Enumerate and refuse to proceed if any reader is missing, naming which.
#   3. Assemble the RAID 0 span by UUID, never by kernel device name.
#   4. Make it swap and enable it.
#
# The array is swap-backed block storage. It is not memory and this script
# does not pretend otherwise; it just tells the kernel to page onto it.
#
#   sudo ./assemble.sh              # assemble, or create on first run
#   sudo ./assemble.sh --create     # force create (DESTROYS DATA)
#   sudo ./assemble.sh --teardown   # swapoff and stop the array
#
set -euo pipefail

FARCE_ROOT="${FARCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_DIR="${FARCE_STATE_DIR:-/etc/farce}"
MD_DEV="${FARCE_MD_DEV:-/dev/md/farce0}"
EXPECT="${FARCE_EXPECT_READERS:-40}"
CHUNK_KB="${FARCE_CHUNK_KB:-512}"
SWAP_PRIORITY="${FARCE_SWAP_PRIORITY:-10}"
STAGE_SIZE="${FARCE_STAGE_SIZE:-8}"
STAGE_DELAY="${FARCE_STAGE_DELAY:-2}"

log() { printf '[assemble] %s\n' "$*"; }
die() { printf '[assemble] FATAL: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }

# ---------------------------------------------------------------- staging ---

stage_power() {
  if ! command -v uhubctl >/dev/null 2>&1; then
    log "uhubctl not installed; cannot gate hub ports."
    log "Readers will have powered up together at boot. If the array is"
    log "unreliable, install uhubctl or power the hubs on by hand, in stages."
    return 0
  fi
  log "staging power-up, ${STAGE_SIZE} ports at a time, ${STAGE_DELAY}s apart"
  # Hubs that support per-port power switching only; others are a no-op.
  local hubs
  hubs=$(uhubctl 2>/dev/null | awk '/^Current status for hub/ {print $5}' || true)
  [ -z "$hubs" ] && { log "no switchable hubs found; continuing"; return 0; }
  for hub in $hubs; do
    uhubctl -l "$hub" -a off >/dev/null 2>&1 || true
  done
  sleep 1
  for hub in $hubs; do
    local port=1
    while [ "$port" -le 10 ]; do
      local last=$(( port + STAGE_SIZE - 1 ))
      uhubctl -l "$hub" -p "${port}-${last}" -a on >/dev/null 2>&1 || true
      sleep "$STAGE_DELAY"
      port=$(( last + 1 ))
    done
  done
  sleep 3
}

# ------------------------------------------------------------ enumeration ---

members() {
  python3 -c '
import json, sys
sys.path.insert(0, "'"$FARCE_ROOT"'")
from farce import enumerate as e
print("\n".join("/dev/" + c["dev"] for c in sorted(e.discover(), key=e.key_of)))
'
}

check_readers() {
  log "enumerating readers"
  if ! python3 -c '
import sys; sys.path.insert(0, "'"$FARCE_ROOT"'")
from farce.enumerate import main; sys.exit(main())
' --check 2>&1 | sed 's/^/[assemble]   /'; then
    log "the saved map and the current devices disagree (see MISSING above)"
  fi

  local found
  found=$(members | grep -c . || true)
  if [ "$found" -ne "$EXPECT" ]; then
    log "found ${found} readers with media, expected ${EXPECT}"
    log "refusing to assemble a partial array."
    log "Run 'python3 -m farce.enumerate --check' to see which slot is missing."
    exit 1
  fi
  log "${found}/${EXPECT} readers present"
}

# ------------------------------------------------------------------ array ---

create_array() {
  local devs; mapfile -t devs < <(members)
  log "creating RAID 0 across ${#devs[@]} devices, ${CHUNK_KB}K chunk"
  log "THIS DESTROYS ALL DATA ON THOSE DEVICES"
  mdadm --create "$MD_DEV" \
        --level=0 --chunk="${CHUNK_KB}" \
        --raid-devices="${#devs[@]}" \
        --name=farce0 --metadata=1.2 \
        "${devs[@]}"
  mkdir -p "$STATE_DIR"
  mdadm --detail --scan "$MD_DEV" > "${STATE_DIR}/mdadm.conf"
  log "wrote ${STATE_DIR}/mdadm.conf"
}

assemble_array() {
  if [ -e "$MD_DEV" ]; then
    log "array already present at ${MD_DEV}"
    return 0
  fi
  if [ -f "${STATE_DIR}/mdadm.conf" ]; then
    log "assembling from ${STATE_DIR}/mdadm.conf"
    mdadm --assemble --scan --config="${STATE_DIR}/mdadm.conf" || true
  fi
  [ -e "$MD_DEV" ] || return 1
}

enable_swap() {
  if swapon --show=NAME --noheadings | grep -qx "$(readlink -f "$MD_DEV")"; then
    log "swap already enabled on ${MD_DEV}"
    return 0
  fi
  if ! blkid -p -u noraid "$MD_DEV" 2>/dev/null | grep -q 'TYPE="swap"'; then
    log "formatting ${MD_DEV} as swap"
    mkswap -L farce0 "$MD_DEV" >/dev/null
  fi
  swapon --priority "$SWAP_PRIORITY" "$MD_DEV"
  log "swap enabled, priority ${SWAP_PRIORITY}"
}

teardown() {
  log "tearing down"
  swapoff "$MD_DEV" 2>/dev/null || true
  mdadm --stop "$MD_DEV" 2>/dev/null || true
  log "done"
  exit 0
}

# ------------------------------------------------------------------- main ---

main() {
  [ "$(id -u)" -eq 0 ] || die "must run as root"
  need mdadm; need mkswap; need swapon; need python3

  case "${1:-}" in
    --teardown) teardown ;;
    --create)   FORCE_CREATE=1 ;;
    "")         FORCE_CREATE=0 ;;
    *)          die "unknown argument: $1" ;;
  esac

  stage_power
  check_readers

  if [ "${FORCE_CREATE}" -eq 1 ]; then
    create_array
  elif ! assemble_array; then
    log "no existing array found; creating one"
    create_array
  fi

  udevadm settle || true
  enable_swap

  log "capacity: $(lsblk -bdno SIZE "$MD_DEV" | awk '{printf "%.2f TB raw\n", $1/1e12}')"
  log "swap now:"
  swapon --show | sed 's/^/[assemble]   /'
}

main "$@"
