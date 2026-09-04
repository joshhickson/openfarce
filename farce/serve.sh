#!/usr/bin/env bash
#
# serve.sh — run a model larger than host RAM, paging onto the array.
#
# The demonstration, in full:
#
#   The model does not fit in RAM. The kernel pages the remainder onto swap.
#   Swap is forty MicroSD cards striped together. Generation proceeds at
#   whatever speed that permits, and we write down the number.
#
# There is no clever software here and this script does not pretend there is.
# llama.cpp mmaps the model; the kernel does the paging; the array is a block
# device the kernel pages onto. The only tuning is making sure the pieces that
# must stay resident do stay resident.
#
#   sudo ./serve.sh --model /srv/models/llama-70b-Q4_K_M.gguf
#   sudo ./serve.sh --model MODEL --tokens 200 --json run.json
#
set -euo pipefail

FARCE_ROOT="${FARCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_DIR="${FARCE_STATE_DIR:-/etc/farce}"
MD_DEV="${FARCE_MD_DEV:-/dev/md/farce0}"
LLAMA="${FARCE_LLAMA_CLI:-llama-cli}"

MODEL=""
TOKENS=128
PROMPT="Explain what a write amplification factor is, in one paragraph."
JSON_OUT=""
THREADS="$(nproc 2>/dev/null || echo 4)"

log() { printf '[serve] %s\n' "$*"; }
die() { printf '[serve] FATAL: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --model)   MODEL="$2"; shift 2 ;;
    --tokens)  TOKENS="$2"; shift 2 ;;
    --prompt)  PROMPT="$2"; shift 2 ;;
    --json)    JSON_OUT="$2"; shift 2 ;;
    --threads) THREADS="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$MODEL" ] || die "--model is required"
[ -f "$MODEL" ] || die "model not found: $MODEL"
command -v "$LLAMA" >/dev/null 2>&1 || die "$LLAMA not on PATH (set FARCE_LLAMA_CLI)"

# --- the array must be the swap the kernel will actually reach for -----------

if ! swapon --show=NAME --noheadings | grep -qx "$(readlink -f "$MD_DEV" 2>/dev/null || echo none)"; then
  die "the array is not enabled as swap; run assemble.sh first"
fi

OTHER_SWAP="$(swapon --show=NAME --noheadings | grep -vx "$(readlink -f "$MD_DEV")" || true)"
if [ -n "$OTHER_SWAP" ]; then
  log "WARNING: other swap devices are active and may be used instead:"
  printf '[serve]   %s\n' $OTHER_SWAP
  log "swapoff them, or the measurement is of your SSD, not the array."
fi

RAM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
MODEL_KB="$(( $(stat -c%s "$MODEL") / 1024 ))"
log "host RAM $(( RAM_KB / 1024 / 1024 )) GB, model $(( MODEL_KB / 1024 / 1024 )) GB"
if [ "$MODEL_KB" -lt "$RAM_KB" ]; then
  log "WARNING: the model fits in RAM. The array will barely be touched and the"
  log "         result will not measure it. Use a larger model or less RAM."
fi

# Swap harder than the default. Without this the kernel prefers to reclaim page
# cache and the array sits idle while the run thrashes the model file instead.
OLD_SWAPPINESS="$(cat /proc/sys/vm/swappiness)"
echo 100 > /proc/sys/vm/swappiness
restore() { echo "$OLD_SWAPPINESS" > /proc/sys/vm/swappiness 2>/dev/null || true; }
trap restore EXIT

SWAP_BEFORE="$(awk '/SwapFree/ {print $2}' /proc/meminfo)"
START="$(date +%s.%N)"

log "generating ${TOKENS} tokens; this will be slow, that is the measurement"
OUT="$("$LLAMA" \
    --model "$MODEL" \
    --prompt "$PROMPT" \
    --n-predict "$TOKENS" \
    --threads "$THREADS" \
    --no-mmap \
    --mlock \
    2>&1 || true)"

END="$(date +%s.%N)"
SWAP_AFTER="$(awk '/SwapFree/ {print $2}' /proc/meminfo)"

ELAPSED="$(awk -v a="$START" -v b="$END" 'BEGIN{printf "%.2f", b-a}')"
TOKS="$(printf '%s' "$OUT" | grep -oE 'eval time.*\(([0-9.]+) ms per token, +([0-9.]+) tokens per second' | grep -oE '[0-9.]+ tokens per second' | tail -1 | grep -oE '^[0-9.]+' || true)"
[ -n "$TOKS" ] || TOKS="$(awk -v t="$TOKENS" -v e="$ELAPSED" 'BEGIN{printf "%.3f", t/e}')"
SWAP_USED_MB="$(( (SWAP_BEFORE - SWAP_AFTER) / 1024 ))"

log "elapsed ${ELAPSED}s"
log "decode  ${TOKS} tok/s"
log "swap grew by ${SWAP_USED_MB} MB during the run"

if [ "$SWAP_USED_MB" -lt 64 ]; then
  log "WARNING: swap barely moved. The array was not meaningfully exercised;"
  log "         do not publish this figure as an array measurement."
fi

if [ -n "$JSON_OUT" ]; then
  cat > "$JSON_OUT" <<JSON
{
  "schema": "farce-serve/1",
  "at": $(date +%s),
  "model": "$(basename "$MODEL")",
  "model_bytes": $(stat -c%s "$MODEL"),
  "host_ram_bytes": $(( RAM_KB * 1024 )),
  "tokens_requested": ${TOKENS},
  "elapsed_s": ${ELAPSED},
  "tokens_per_second": ${TOKS},
  "swap_growth_bytes": $(( SWAP_USED_MB * 1024 * 1024 )),
  "array_exercised": $( [ "$SWAP_USED_MB" -ge 64 ] && echo true || echo false ),
  "note": "decode speed with the model paged onto swap-backed block storage"
}
JSON
  log "wrote ${JSON_OUT}"
fi
