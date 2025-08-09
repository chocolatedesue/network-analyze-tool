#!/usr/bin/env bash
# tuning.sh - Apply kernel & sysfs tuning for large-scale FRR + many containers
# Usage: sudo ./tuning.sh
# Edit variables below to match your system before running.

set -euo pipefail

# ---- USER CONFIG ----
# CPU mask for RPS/XPS (hex). Example "ff" (use CPUs 0..7). Choose mask carefully.
# You can also set CPU_MASK="" to skip setting CPU masks.
CPU_MASK="${CPU_MASK:-ff}"

# Which NICs to operate on. By default we try to auto-detect non-loopback NICs.
# You can set NICS="eth0 ens1f0" to target specific NIC names.
NICS="${NICS:-$(ls /sys/class/net | grep -v lo | tr '\n' ' ')}"

# FRR systemd service name (common packaging uses 'frr' or 'frr.service')
FRR_SERVICE_NAME="${FRR_SERVICE_NAME:-frr.service}"

# Sysctl conf path
SYSCTL_CONF="/etc/sysctl.d/99-frr-tuning.conf"

# Limits conf
LIMITS_CONF="/etc/security/limits.d/99-frr-limits.conf"
SYSTEMD_CONF="/etc/systemd/system.conf.d/99-frr-limits.conf"

TMPFILES_RPS="/etc/tmpfiles.d/rps.conf"
RPS_SERVICE="/usr/local/sbin/rps-xps-apply.sh"

BACKUP_DIR="/root/frr-tuning-backups-$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "Backup directory: $BACKUP_DIR"

# ---- 1) Write sysctl baseline (no reboot required) ----
echo "Writing sysctl conf to $SYSCTL_CONF (backup old file if exists)..."
if [ -f "$SYSCTL_CONF" ]; then
  cp -a "$SYSCTL_CONF" "$BACKUP_DIR/$(basename $SYSCTL_CONF).bak"
fi

cat > "$SYSCTL_CONF" <<'EOF'
# FRR kernel tuning baseline - safe defaults
# Apply: sysctl --system  (this applies immediately)
net.core.rmem_default = 4194304
net.core.wmem_default = 4194304
net.core.rmem_max     = 67108864
net.core.wmem_max     = 67108864
net.core.netdev_max_backlog = 250000
net.core.somaxconn = 4096

# TCP tuning for lots of BGP sessions
net.ipv4.tcp_rmem = 4096 262144 33554432
net.ipv4.tcp_wmem = 4096 262144 33554432
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.ip_local_port_range = 1024 65000
net.ipv4.tcp_timestamps = 1
net.ipv4.tcp_sack = 1
net.ipv4.tcp_syncookies = 1

# Neighbor scaling (IPv4 & IPv6)
net.ipv4.neigh.default.gc_thresh1 = 4096
net.ipv4.neigh.default.gc_thresh2 = 8192
net.ipv4.neigh.default.gc_thresh3 = 16384
net.ipv6.neigh.default.gc_thresh1 = 4096
net.ipv6.neigh.default.gc_thresh2 = 8192
net.ipv6.neigh.default.gc_thresh3 = 16384

# Multipath (if kernel supports it)
net.ipv4.fib_multipath_hash_policy = 1
net.ipv6.fib_multipath_hash_policy = 1
net.ipv4.fib_multipath_use_neigh = 1

# Router defaults
net.ipv4.ip_forward = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.forwarding = 1
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.default.accept_ra = 0

# File descriptors / swapping / pids / maps
fs.file-max = 2000000
vm.swappiness = 1
# increase max map count (helpful with many processes/containers)
vm.max_map_count = 262144
# allow large pid space if you expect many processes (can be tuned)
kernel.pid_max = 4194303

# inotify/watch count for many containers/apps that open many watches
fs.inotify.max_user_watches = 524288

EOF

cat >> "$SYSCTL_CONF" <<'EOF'

# ---- Large-scale increments (enable if needed) ----
# Uncomment or copy these to the conf only after testing:
# net.core.rmem_max=134217728
# net.core.wmem_max=134217728
# net.ipv4.tcp_rmem=4096 1048576 67108864
# net.ipv4.tcp_wmem=4096 1048576 67108864
# net.core.netdev_max_backlog=500000
# net.ipv4.neigh.default.gc_thresh1=8192
# net.ipv4.neigh.default.gc_thresh2=32768
# net.ipv4.neigh.default.gc_thresh3=65536
EOF

echo "Applying sysctl settings now (sysctl --system)..."
sysctl --system >/dev/null

echo "Verifying some sysctl values:"
sysctl net.core.rmem_max net.core.netdev_max_backlog fs.file-max vm.swappiness kernel.pid_max fs.inotify.max_user_watches || true

cat <<'NOTE'

Sysctl notes:
- These sysctl changes are applied immediately by `sysctl --system`. **NO REBOOT required**.
- To roll back, restore the backup in $BACKUP_DIR and run `sysctl --system`.
NOTE

# ---- 2) System limits for FD / NPROC and systemd defaults ----
echo "Configuring systemd & PAM limits (no reboot required for system services; interactive users must re-login)..."

# Backup existing files
if [ -f "$LIMITS_CONF" ]; then
  cp -a "$LIMITS_CONF" "$BACKUP_DIR/$(basename $LIMITS_CONF).bak"
fi

cat > "$LIMITS_CONF" <<'EOF'
# high limits for FRR and container hosting
* soft nofile 200000
* hard nofile 200000
* soft nproc 65536
* hard nproc 65536
root soft nofile 200000
root hard nofile 200000
EOF

echo "Created $LIMITS_CONF"

# systemd default limits (so services started by systemd get higher limits)
mkdir -p "$(dirname "$SYSTEMD_CONF")"
if [ -f "$SYSTEMD_CONF" ]; then
  cp -a "$SYSTEMD_CONF" "$BACKUP_DIR/$(basename $SYSTEMD_CONF).bak"
fi

cat > "$SYSTEMD_CONF" <<'EOF'
[Manager]
# Default limits for services started by systemd
DefaultLimitNOFILE=200000
DefaultLimitNPROC=65536
EOF

echo "Created $SYSTEMD_CONF (systemd manager defaults). Running systemctl daemon-reload..."

systemctl daemon-reload

cat <<'NOTE'

Limits notes:
- System services started AFTER these settings will inherit the new limits.
- **Service restart required** for the settings to affect a service (e.g., restart frr.service, container runtime).
- Interactive sessions (ssh shells) need re-login to pick up PAM limits; **no full reboot required**.
NOTE

# ---- 3) FRR systemd drop-in: MALLOC_ARENA_MAX + affinity helpers ----
# This helps long-running FRR processes avoid heap fragmentation spikes.
FRR_DROPIN_DIR="/etc/systemd/system/${FRR_SERVICE_NAME}.d"
mkdir -p "$FRR_DROPIN_DIR"

FRR_DROPIN_FILE="$FRR_DROPIN_DIR/50-frr-memory.conf"
if [ -f "$FRR_DROPIN_FILE" ]; then
  cp -a "$FRR_DROPIN_FILE" "$BACKUP_DIR/$(basename $FRR_DROPIN_FILE).bak"
fi

cat > "$FRR_DROPIN_FILE" <<EOF
[Service]
Environment=MALLOC_ARENA_MAX=4
LimitNOFILE=200000
LimitNPROC=65536
# Optionally set CPUAffinity to dedicate CPUs for FRR daemons (uncomment and set mask)
# CPUAffinity=0 1
# To pin more specifically, see systemd docs or use taskset when launching.
EOF

echo "Created systemd drop-in for $FRR_SERVICE_NAME at $FRR_DROPIN_FILE"
systemctl daemon-reload

cat <<'NOTE'

FRR service notes:
- After this change, restart FRR to pick up MALLOC_ARENA_MAX and limits:
    sudo systemctl restart ${FRR_SERVICE_NAME}
- **No reboot required**. Restarting the FRR service is sufficient.
NOTE

# ---- 4) Apply per-NIC RPS/XPS and rps_sock_flow_entries ----
apply_rps_xps_now() {
  echo "Applying RPS/XPS settings to NICs: $NICS (using CPU_MASK=$CPU_MASK)"
  # write rps_sock_flow_entries
  echo 32768 > /proc/sys/net/core/rps_sock_flow_entries || true

  for nic in $NICS; do
    # find rx queues:
    rxqueues=$(ls /sys/class/net/"$nic"/queues 2>/dev/null | grep rx || true)
    txqueues=$(ls /sys/class/net/"$nic"/queues 2>/dev/null | grep tx || true)
    if [ -z "$rxqueues" ] && [ -z "$txqueues" ]; then
      echo "  -> no queues found for $nic, skipping"
      continue
    fi

    for q in $rxqueues; do
      path="/sys/class/net/$nic/queues/$q/rps_cpus"
      if [ -w "$path" ]; then
        echo "$CPU_MASK" > "$path" || true
      fi
      path2="/sys/class/net/$nic/queues/$q/rps_flow_cnt"
      if [ -w "$path2" ]; then
        echo 32768 > "$path2" || true
      fi
    done

    for q in $txqueues; do
      path="/sys/class/net/$nic/queues/$q/xps_cpus"
      if [ -w "$path" ]; then
        echo "$CPU_MASK" > "$path" || true
      fi
    done

    echo "  -> RPS/XPS applied on $nic"
  done
}

# create a small helper script to reapply at boot (tmpfiles + init script alternative)
cat > "$RPS_SERVICE" <<'EOF'
#!/usr/bin/env bash
# apply RPS/XPS at boot (called by tmpfiles or by admin)
CPU_MASK="${CPU_MASK:-ff}"
NICS="${NICS:-$(ls /sys/class/net | grep -v lo | tr '\n' ' ')}"

echo 32768 > /proc/sys/net/core/rps_sock_flow_entries || true

for nic in $NICS; do
  rxqueues=$(ls /sys/class/net/"$nic"/queues 2>/dev/null | grep rx || true)
  txqueues=$(ls /sys/class/net/"$nic"/queues 2>/dev/null | grep tx || true)
  for q in $rxqueues; do
    path="/sys/class/net/$nic/queues/$q/rps_cpus"
    if [ -w "$path" ]; then
      echo "$CPU_MASK" > "$path" || true
    fi
    path2="/sys/class/net/$nic/queues/$q/rps_flow_cnt"
    if [ -w "$path2" ]; then
      echo 32768 > "$path2" || true
    fi
  done
  for q in $txqueues; do
    path="/sys/class/net/$nic/queues/$q/xps_cpus"
    if [ -w "$path" ]; then
      echo "$CPU_MASK" > "$path" || true
    fi
  done
done
EOF

chmod +x "$RPS_SERVICE" || true
cp "$RPS_SERVICE" "$BACKUP_DIR/"

# tmpfiles entry that runs RPS script at boot
cat > "$TMPFILES_RPS" <<EOF
# Type Path Mode UID GID Age Argument
R! /usr/local/sbin/rps-xps-apply.sh - - - - - - /usr/local/sbin/rps-xps-apply.sh
EOF

# Copy helper into /usr/local/sbin so tmpfiles can run it
mv "$RPS_SERVICE" /usr/local/sbin/rps-xps-apply.sh
chown root:root /usr/local/sbin/rps-xps-apply.sh
chmod 755 /usr/local/sbin/rps-xps-apply.sh

# Apply now
apply_rps_xps_now

echo "Created $TMPFILES_RPS and /usr/local/sbin/rps-xps-apply.sh to persist RPS/XPS at boot (via systemd-tmpfiles)."
echo "To apply at boot you may need: systemd-tmpfiles --create"

cat <<'NOTE'

RPS/XPS notes:
- The script applied RPS/XPS immediately. **NO REBOOT required**.
- The tmpfiles entry will reapply at boot (no persistent kernel change required).
- Choose CPU_MASK carefully (it is a hex mask of CPUs). Wrong mask = no CPU selected.
NOTE

# ---- 5) NIC offloads (ethtool). These are immediate; persistent via network scripts if needed ----
echo "Applying recommended NIC offload settings via ethtool (per NIC)."
echo "This script will attempt: disable LRO, enable GRO, leave TSO/GSO as-is (adjust as needed)."

for nic in $NICS; do
  if ! command -v ethtool >/dev/null 2>&1; then
    echo "ethtool not installed; skipping offload tuning. Install ethtool if you want to tune offloads."
    break
  fi
  # attempt apply; not all NICs support these flags
  echo "Applying offload settings on $nic"
  ethtool -K "$nic" lro off 2>/dev/null || true
  ethtool -K "$nic" gro on 2>/dev/null || true
  # keep TSO/GSO per your data-plane requirements; often good to keep on
  # ethtool -K "$nic" tso on gso on 2>/dev/null || true
done

cat <<'NOTE'

NIC offload notes:
- Changes via ethtool take effect immediately. **NO REBOOT required**.
- To make them persistent, add them to your network config (Netplan, NetworkManager, ifupdown, or udev rules).
- Test latency & throughput after changes — LRO off can increase CPU on Rx path but decrease reordering effects for routers.
NOTE

# ---- 6) Transparent Hugepages and other /sys toggles ----
echo "Tuning transparent hugepages (THP) -> set to 'madvise' (immediate)."
if [ -w /sys/kernel/mm/transparent_hugepage/enabled ]; then
  echo madvise > /sys/kernel/mm/transparent_hugepage/enabled || true
fi
if [ -w /sys/kernel/mm/transparent_hugepage/defrag ]; then
  echo madvise > /sys/kernel/mm/transparent_hugepage/defrag || true
fi

cat <<'NOTE'

THP notes:
- These writes take effect immediately. **NO REBOOT required**.
- To persist across reboot, add a small systemd tmpfile or grub kernel param depends on distro (we didn't change grub).
NOTE

# ---- 7) Final notes, service restarts, and verification guidance ----
echo
echo "DONE applying changes. Summary of required restarts:"
echo " - sysctl changes: applied immediately. NO reboot."
echo " - RPS/XPS: applied immediately and tmpfiles set to reapply at boot. NO reboot."
echo " - ethtool offloads: applied immediately. NO reboot (but persistent config across reboots requires network config changes)."
echo " - systemd manager defaults and FRR drop-in: systemctl daemon-reload done. To fully apply to FRR, restart the FRR service:"
echo "       sudo systemctl restart ${FRR_SERVICE_NAME}"
echo " - Interactive user shells: re-login required to pick up new PAM limits."
echo " - A full REBOOT is NOT required for any of the settings above. Reboot only if you change kernel boot parameters or swap in a new kernel."

echo
echo "Suggested verification commands:"
echo " sysctl -a | egrep 'rmem|wmem|backlog|somaxconn|gc_thresh|fib_multipath|pid_max|inotify|max_map_count'"
echo " ss -s"
echo " ip -s link"
echo " cat /proc/sys/net/core/rps_sock_flow_entries"
echo " for nic in $NICS; do ethtool -k \$nic; done"
echo " systemctl status ${FRR_SERVICE_NAME}"
echo " journalctl -u ${FRR_SERVICE_NAME} -n 200"

echo
echo "If you want me to:
 - tune the 'large-scale' increments now (bigger rmem, bigger neigh tables), or
 - generate exact CPU masks from your CPU count,
 - produce persistent udev/systemd-udev rules for NIC offloads,
 - or tune PID/file-max values specifically for 15k containers (need exact expected process-per-container),
then tell me your kernel version, total CPU cores, amount of RAM, NIC model(s), and container runtime (crun/podman/containerd) and I will tailor exact values."

exit 0
