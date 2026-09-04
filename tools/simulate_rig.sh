#!/usr/bin/env bash
#
# simulate_rig.sh — build a fake array out of loop devices.
#
# There is no hardware yet. This creates N sparse files, attaches them as loop
# devices, and assembles them exactly as assemble.sh would, so that bench.py,
# endure.py and thermal.py can be developed and tested against something real
# enough to exercise every code path.
#
# What it proves:  the tooling runs, the ledger accumulates, the JSON is valid,
#                  the systemd units start, the counter publishes.
# What it does NOT prove:  anything at all about MicroSD cards. Loop devices on
#                  an SSD are thousands of times faster and do not wear out.
#                  NO NUMBER PRODUCED FROM A SIMULATED RIG MAY BE PUBLISHED.
#
#   sudo ./tools/simulate_rig.sh up 40
#   sudo ./tools/simulate_rig.sh down
#
set -euo pipefail

WORK="${FARCE_SIM_DIR:-/var/tmp/farce-sim}"
SIZE_MB="${FARCE_SIM_SIZE_MB:-64}"
MD_DEV="${FARCE_MD_DEV:-/dev/md/farcesim0}"

log() { printf '[sim] %s\n' "$*"; }

up() {
  local n="${1:-40}"
  log "creating ${n} loop devices of ${SIZE_MB} MB in ${WORK}"
  mkdir -p "$WORK"
  local devs=()
  for i in $(seq 1 "$n"); do
    local f
    f="$(printf '%s/card%02d.img' "$WORK" "$i")"
    [ -f "$f" ] || truncate -s "${SIZE_MB}M" "$f"
    devs+=("$(losetup --find --show "$f")")
  done
  log "attached: ${devs[*]:0:4} ... (${#devs[@]} total)"

  log "assembling RAID 0"
  mdadm --create "$MD_DEV" --level=0 --chunk=512 \
        --raid-devices="${#devs[@]}" --name=farcesim0 --metadata=1.2 \
        --run "${devs[@]}"

  log "array: $(lsblk -bdno SIZE "$MD_DEV" | awk '{printf "%.2f GB", $1/1e9}')"
  log ""
  log "SIMULATED. Do not publish any measurement taken from this array."
  log ""
  log "  sudo FARCE_MD_DEV=$MD_DEV python3 -m farce.bench --array --runtime 10"
  log "  sudo FARCE_STATE_DIR=$WORK/state python3 -m farce.endure --status"
}

down() {
  log "tearing down"
  swapoff "$MD_DEV" 2>/dev/null || true
  mdadm --stop "$MD_DEV" 2>/dev/null || true
  for dev in $(losetup -a | awk -F: -v w="$WORK" '$0 ~ w {print $1}'); do
    losetup -d "$dev" 2>/dev/null || true
  done
  log "loop devices detached; images kept in ${WORK}"
  log "rm -rf ${WORK} to discard them"
}

[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }
case "${1:-}" in
  up)   up "${2:-40}" ;;
  down) down ;;
  *)    echo "usage: $0 {up [count]|down}" >&2; exit 1 ;;
esac
