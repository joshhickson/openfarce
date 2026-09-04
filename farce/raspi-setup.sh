#!/usr/bin/env bash
#
# raspi-setup.sh — take a clean Raspberry Pi OS image to a host that can run the
# reference rig. Addendum A2.1.3.
#
# Everything here has a reason, and the reasons are in the comments, because
# most of these settings look like superstition until the thing they prevent
# happens at 2 a.m. on the third day of an endurance run.
#
#   sudo ./raspi-setup.sh              # apply
#   sudo ./raspi-setup.sh --check      # report what is and is not applied
#
# Reboot afterwards. Nothing here is undone automatically; the settings it
# changes are listed at the end so they can be reversed by hand.
set -euo pipefail

CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

log()  { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] WARN: %s\n' "$*" >&2; }
die()  { printf '[setup] FATAL: %s\n' "$*" >&2; exit 1; }

ok()   { printf '[setup]   %-46s %s\n' "$1" "${2:-ok}"; }

BOOT_CONFIG=/boot/firmware/config.txt
[ -f "$BOOT_CONFIG" ] || BOOT_CONFIG=/boot/config.txt

SYSCTL_FILE=/etc/sysctl.d/99-farce.conf

PACKAGES="mdadm fio smartmontools stress-ng htop python3-pip uhubctl"

# --------------------------------------------------------------------- check --

report() {
  log "checking, changing nothing"
  ok "boot config" "$BOOT_CONFIG"
  if grep -q '^usb_max_current_enable=1' "$BOOT_CONFIG" 2>/dev/null; then
    ok "usb_max_current_enable=1" "present"
  else
    ok "usb_max_current_enable=1" "MISSING"
  fi
  for p in $PACKAGES; do
    if dpkg -s "$p" >/dev/null 2>&1; then ok "$p" "installed"; else ok "$p" "MISSING"; fi
  done
  if systemctl is-enabled zramswap >/dev/null 2>&1; then
    ok "zramswap" "STILL ENABLED — swap would not reach the array"
  else
    ok "zramswap" "off"
  fi
  [ -f "$SYSCTL_FILE" ] && ok "$SYSCTL_FILE" "present" || ok "$SYSCTL_FILE" "MISSING"
  ok "vm.swappiness" "$(cat /proc/sys/vm/swappiness)"
  command -v llama-cli >/dev/null 2>&1 && ok "llama-cli" "on PATH" || ok "llama-cli" "not built"
  exit 0
}

[ "$CHECK" -eq 1 ] && report

# --------------------------------------------------------------------- apply --

[ "$(id -u)" -eq 0 ] || die "must run as root"

if ! grep -qi 'raspbian\|raspberry' /etc/os-release 2>/dev/null; then
  warn "this does not look like Raspberry Pi OS. Continuing, but the boot"
  warn "config path and the zram unit name are Pi-specific and may not apply."
fi

log "installing packages"
apt-get update -qq
# shellcheck disable=SC2086
apt-get install -y -qq $PACKAGES || warn "some packages failed; check above"

# The Pi supplies about 1.2 A across all its USB ports. With a self-powered hub
# this changes nothing, and it is set anyway so that a reader plugged straight
# into the Pi during debugging does not brown out and look like a dead card.
if ! grep -q '^usb_max_current_enable=1' "$BOOT_CONFIG"; then
  log "setting usb_max_current_enable=1 in $BOOT_CONFIG"
  printf '\n# Added by openfarce raspi-setup.sh\nusb_max_current_enable=1\n' >> "$BOOT_CONFIG"
else
  log "usb_max_current_enable already set"
fi

# zram is compressed swap in RAM. It is a good default and it is exactly wrong
# here: with zram enabled the kernel satisfies swap from memory and the array
# is never touched, so the demo would measure nothing and report a number that
# looks impressively fast. This is the single most important line in the file.
if systemctl list-unit-files 2>/dev/null | grep -q '^zramswap'; then
  log "disabling zramswap so swap reaches the array"
  systemctl disable --now zramswap || warn "could not disable zramswap"
else
  log "no zramswap unit; nothing to disable"
fi

# dphys-swapfile is the Pi's file-backed swap. Leaving it on gives the kernel a
# faster swap device than the array, and it will prefer it, for the same reason.
if systemctl list-unit-files 2>/dev/null | grep -q '^dphys-swapfile'; then
  log "disabling dphys-swapfile so the array is the only swap"
  systemctl disable --now dphys-swapfile || warn "could not disable dphys-swapfile"
fi

log "writing $SYSCTL_FILE"
cat > "$SYSCTL_FILE" <<'SYSCTL'
# openfarce — reference rig tuning. See farce/raspi-setup.sh for the reasoning.

# The demo profile wants the kernel to reach for the array eagerly. serve.sh
# sets this per run (10 for demo-fits, 100 for demo-swaps); this is the resting
# value between runs and is deliberately sane rather than dramatic.
vm.swappiness = 10

# Swap on high-latency media benefits from reading more than one page at a
# time, because the cost is dominated by the round trip, not the bytes.
# 3 means 2^3 = 8 pages per fault.
vm.page-cluster = 3

# Do not let the machine become unresponsive before the OOM killer acts. An
# endurance run that wedges the Pi produces no data and needs a power cycle.
vm.watermark_boost_factor = 0
SYSCTL
sysctl -p "$SYSCTL_FILE" >/dev/null || warn "sysctl reload failed"

log ""
log "done. Reboot for the boot config change to take effect."
log ""
log "Changed:"
log "  $BOOT_CONFIG          usb_max_current_enable=1 appended"
log "  zramswap              disabled (was hiding the array from swap)"
log "  dphys-swapfile        disabled if present"
log "  $SYSCTL_FILE   created"
log "  packages              $PACKAGES"
log ""
log "Not done here: building llama.cpp. It takes a while and it is not"
log "needed until serve.sh runs. See docs/reference-rig.md."
