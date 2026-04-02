#!/usr/bin/env bash
# =============================================================================
# AUTOBOT V2 — Kernel tuning via sysctl
# P5: OS-level optimizations for low-latency trading
#
# Usage:
#   sudo bash sysctl_config.sh             # apply all settings
#   sudo bash sysctl_config.sh dry-run     # print settings without applying
#   sudo bash sysctl_config.sh restore     # revert to saved baseline
#
# Requirements:
#   - Linux kernel ≥ 4.5 (for SO_BUSY_POLL / tcp_early_retrans)
#   - Root privileges (sudo)
#
# Safety notes:
#   - A baseline snapshot is saved to /tmp/autobot_sysctl_baseline.conf
#     before any changes, enabling one-command restore.
#   - All changes are in-memory only (reset on reboot unless written to
#     /etc/sysctl.d/99-autobot.conf via the --persist flag).
#   - Tested on Debian/Ubuntu/RHEL with kernel 5.x and 6.x.
# =============================================================================

set -euo pipefail

BASELINE="/tmp/autobot_sysctl_baseline.conf"
PERSIST_FILE="/etc/sysctl.d/99-autobot.conf"
MODE="${1:-apply}"

# ---------------------------------------------------------------------------
# Parameter definitions
# Format: "key=value  # comment"
# ---------------------------------------------------------------------------
declare -A PARAMS=(
  # -- TCP TIME_WAIT socket reuse -------------------------------------------
  # Allows the kernel to reuse TCP sockets in TIME_WAIT state for new
  # outbound connections. Prevents port exhaustion under high connection rate.
  ["net.ipv4.tcp_tw_reuse"]="1"

  # -- Connection backlog ----------------------------------------------------
  # Maximum number of pending connections in the accept queue.
  # Default is typically 128; raise to 65535 for high-throughput services.
  ["net.core.somaxconn"]="65535"

  # -- TCP SYN backlog -------------------------------------------------------
  # Maximum number of queued SYN requests (half-open connections).
  ["net.ipv4.tcp_max_syn_backlog"]="65535"

  # -- Swap avoidance --------------------------------------------------------
  # vm.swappiness=1 makes the kernel strongly prefer RAM over swap.
  # A GC-paused process that gets swapped out will see latency spikes.
  ["vm.swappiness"]="1"

  # -- TCP receive / send buffer sizes (8 MB) --------------------------------
  # Larger buffers absorb burst traffic without dropping packets.
  ["net.core.rmem_max"]="8388608"
  ["net.core.wmem_max"]="8388608"
  ["net.ipv4.tcp_rmem"]="4096 87380 8388608"
  ["net.ipv4.tcp_wmem"]="4096 65536 8388608"

  # -- TCP fast-open (Linux ≥ 3.7) ------------------------------------------
  # Reduces handshake latency for repeated connections to the same server.
  # 3 = enable for both outbound (client) and inbound (server) connections.
  ["net.ipv4.tcp_fastopen"]="3"

  # -- Interrupt coalescing budget ------------------------------------------
  # Raise the softirq budget so the kernel drains more packets per interrupt.
  # Reduces interrupt-processing overhead at high packet rates.
  ["net.core.netdev_budget"]="600"
  ["net.core.netdev_budget_usecs"]="8000"

  # -- Busy-read timeout (µs) -----------------------------------------------
  # When > 0, the kernel performs a busy-wait on socket receives before
  # sleeping.  Works in concert with SO_BUSY_POLL (set per-socket in Python).
  ["net.core.busy_read"]="50"
  ["net.core.busy_poll"]="50"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { printf '[AUTOBOT sysctl] %s\n' "$*"; }
warn() { printf '[AUTOBOT sysctl] WARNING: %s\n' "$*" >&2; }
fail() { printf '[AUTOBOT sysctl] ERROR: %s\n' "$*" >&2; exit 1; }

check_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    fail "This script must be run as root (sudo bash $0)"
  fi
}

save_baseline() {
  log "Saving baseline to ${BASELINE}..."
  : > "${BASELINE}"
  for key in "${!PARAMS[@]}"; do
    current=$(sysctl -n "${key}" 2>/dev/null || echo "UNAVAILABLE")
    printf '%s=%s\n' "${key}" "${current}" >> "${BASELINE}"
  done
  log "Baseline saved."
}

apply_params() {
  local dry="${1:-false}"
  local applied=0 skipped=0

  # SEC-05: warn about high-impact parameters before applying
  if [[ "${dry}" != "true" ]]; then
    warn "Applying kernel parameters that affect system security and stability."
    warn "net.core.somaxconn=65535 increases attack surface for SYN-flood attacks."
    warn "Ensure a firewall (iptables/nftables) is active before applying."
  fi

  for key in "${!PARAMS[@]}"; do
    val="${PARAMS[$key]}"
    if [[ "${dry}" == "true" ]]; then
      printf '  [DRY-RUN] %s = %s\n' "${key}" "${val}"
      (( applied++ )) || true
    else
      if sysctl -w "${key}=${val}" &>/dev/null; then
        log "  SET  ${key} = ${val}"
        (( applied++ )) || true
      else
        warn "  SKIP ${key} (not available on this kernel)"
        (( skipped++ )) || true
      fi
    fi
  done

  log "Done: ${applied} applied, ${skipped} skipped."
}

restore_baseline() {
  if [[ ! -f "${BASELINE}" ]]; then
    fail "No baseline found at ${BASELINE}. Run 'apply' first."
  fi
  log "Restoring baseline from ${BASELINE}..."
  while IFS='=' read -r key val; do
    if [[ "${val}" == "UNAVAILABLE" ]]; then
      log "  SKIP ${key} (was unavailable at baseline)"
      continue
    fi
    sysctl -w "${key}=${val}" &>/dev/null && log "  RESTORED ${key} = ${val}" \
      || warn "  COULD NOT restore ${key}"
  done < "${BASELINE}"
  log "Restore complete."
}

persist_settings() {
  log "Persisting settings to ${PERSIST_FILE}..."
  {
    printf '# AUTOBOT V2 sysctl settings — generated by sysctl_config.sh\n'
    printf '# Apply manually: sysctl -p %s\n\n' "${PERSIST_FILE}"
    for key in "${!PARAMS[@]}"; do
      printf '%s = %s\n' "${key}" "${PARAMS[$key]}"
    done
  } > "${PERSIST_FILE}"
  log "Written to ${PERSIST_FILE}. Reload with: sysctl --system"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

case "${MODE}" in
  apply)
    check_root
    save_baseline
    log "Applying ${#PARAMS[@]} sysctl parameters..."
    apply_params false
    if [[ "${2:-}" == "--persist" ]]; then
      persist_settings
    fi
    ;;
  dry-run)
    log "Dry-run — no changes will be made:"
    apply_params true
    ;;
  restore)
    check_root
    restore_baseline
    ;;
  *)
    printf 'Usage: %s [apply|dry-run|restore] [--persist]\n' "$0" >&2
    exit 1
    ;;
esac
