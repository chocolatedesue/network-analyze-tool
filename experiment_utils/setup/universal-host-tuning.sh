#!/bin/bash

# =============================================================================
# Universal Host Kernel Tuning Script
# =============================================================================
# A standalone, reusable kernel tuning script for single-machine deployments
# that need to run large numbers of containers and complex networking.
# 
# Compatible with: Ubuntu, CentOS, RHEL, Debian, and other Linux distributions
# Use case: Container orchestration, network simulation, high-density deployments
# =============================================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Script metadata
SCRIPT_VERSION="1.0"
SCRIPT_NAME="Universal Host Kernel Tuning"
CONFIG_FILE="/etc/sysctl.d/99-universal-host-tuning.conf"
BACKUP_DIR="/etc/sysctl.d/backups"

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
        echo "Usage: sudo $0 [command]"
        exit 1
    fi
}

# Detect system information
detect_system() {
    log "Detecting system information..."
    
    # OS Detection
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_NAME="$NAME"
        OS_VERSION="$VERSION_ID"
    else
        OS_NAME="Unknown"
        OS_VERSION="Unknown"
    fi
    
    # Kernel version
    KERNEL_VERSION=$(uname -r)
    
    # Memory size
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_GB=$((TOTAL_MEM_KB / 1024 / 1024))
    
    # CPU cores
    CPU_CORES=$(nproc)
    
    info "OS: $OS_NAME $OS_VERSION"
    info "Kernel: $KERNEL_VERSION"
    info "Memory: ${TOTAL_MEM_GB}GB"
    info "CPU Cores: $CPU_CORES"
}

# Create backup of current settings
backup_current_settings() {
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_file="$BACKUP_DIR/sysctl-backup-$timestamp.conf"
    
    log "Creating backup of current settings..."
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Backup current sysctl settings
    {
        echo "# Universal Host Kernel Tuning Backup"
        echo "# Created: $(date)"
        echo "# System: $OS_NAME $OS_VERSION"
        echo "# Kernel: $KERNEL_VERSION"
        echo ""
        
        # Critical settings backup
        echo "# Original settings before tuning"
        sysctl -a 2>/dev/null | grep -E "(kernel\.pty\.max|net\.ipv4\.ip_forward|net\.ipv4\.neigh\.default\.gc_thresh|net\.nf_conntrack_max|net\.core\.)" || true
        
    } > "$backup_file"
    
    log "✓ Backup saved to: $backup_file"
}

# Apply kernel tuning optimizations
apply_kernel_tuning() {
    log "Applying universal host kernel tuning..."
    
    # =================================================================
    # Container and Process Limits
    # =================================================================
    log "Optimizing container and process limits..."
    
    # Support for large number of containers/processes
    sysctl -w kernel.pty.max=131072
    log "✓ Increased PTY limit to 131K (container support)"
    
    # Process limits
    sysctl -w kernel.pid_max=4194304
    log "✓ Increased PID max to 4M processes"
    
    # =================================================================
    # Network Stack Core Optimizations
    # =================================================================
    log "Optimizing network stack core..."
    
    # Enable IP forwarding (essential for routing/bridging)
    sysctl -w net.ipv4.ip_forward=1
    sysctl -w net.ipv6.conf.all.forwarding=1
    log "✓ Enabled IP forwarding (IPv4/IPv6)"
    
    # Disable reverse path filtering (support complex routing)
    sysctl -w net.ipv4.conf.all.rp_filter=0
    sysctl -w net.ipv4.conf.default.rp_filter=0
    log "✓ Disabled reverse path filtering"
    
    # Network device queue optimizations
    sysctl -w net.core.netdev_max_backlog=30000
    sysctl -w net.core.netdev_budget=600
    sysctl -w net.core.netdev_budget_usecs=8000
    log "✓ Optimized network device queues"
    
    # =================================================================
    # Memory and Buffer Optimizations
    # =================================================================
    log "Optimizing memory and network buffers..."
    
    # Socket buffer limits (scale with available memory)
    local rmem_max=$((TOTAL_MEM_GB * 1024 * 1024))  # 1MB per GB of RAM
    local wmem_max=$rmem_max
    
    # Ensure minimum values
    [[ $rmem_max -lt 16777216 ]] && rmem_max=16777216  # Min 16MB
    [[ $wmem_max -lt 16777216 ]] && wmem_max=16777216  # Min 16MB
    
    sysctl -w net.core.rmem_default=262144
    sysctl -w net.core.rmem_max=$rmem_max
    sysctl -w net.core.wmem_default=262144
    sysctl -w net.core.wmem_max=$wmem_max
    log "✓ Optimized socket buffers (max: ${rmem_max} bytes)"
    
    # TCP buffer optimizations
    sysctl -w net.ipv4.tcp_rmem="4096 65536 $rmem_max"
    sysctl -w net.ipv4.tcp_wmem="4096 65536 $wmem_max"
    log "✓ Optimized TCP buffers"
    
    # =================================================================
    # Neighbor Table Optimizations (ARP/NDP)
    # =================================================================
    log "Optimizing neighbor tables..."
    
    # Scale neighbor table with memory (but cap at reasonable limits)
    local neigh_thresh1=$((TOTAL_MEM_GB * 32768))   # 32K per GB
    local neigh_thresh2=$((TOTAL_MEM_GB * 131072))  # 128K per GB
    local neigh_thresh3=$((TOTAL_MEM_GB * 262144))  # 256K per GB
    
    # Apply caps
    [[ $neigh_thresh1 -gt 1048576 ]] && neigh_thresh1=1048576    # Max 1M
    [[ $neigh_thresh2 -gt 4194304 ]] && neigh_thresh2=4194304    # Max 4M
    [[ $neigh_thresh3 -gt 8388608 ]] && neigh_thresh3=8388608    # Max 8M
    
    # Ensure minimums
    [[ $neigh_thresh1 -lt 32768 ]] && neigh_thresh1=32768        # Min 32K
    [[ $neigh_thresh2 -lt 131072 ]] && neigh_thresh2=131072      # Min 128K
    [[ $neigh_thresh3 -lt 262144 ]] && neigh_thresh3=262144      # Min 256K
    
    # IPv4 neighbor table
    sysctl -w net.ipv4.neigh.default.gc_thresh1=$neigh_thresh1
    sysctl -w net.ipv4.neigh.default.gc_thresh2=$neigh_thresh2
    sysctl -w net.ipv4.neigh.default.gc_thresh3=$neigh_thresh3
    log "✓ Optimized IPv4 neighbor table (${neigh_thresh3} max entries)"
    
    # IPv6 neighbor table
    sysctl -w net.ipv6.neigh.default.gc_thresh1=$neigh_thresh1
    sysctl -w net.ipv6.neigh.default.gc_thresh2=$neigh_thresh2
    sysctl -w net.ipv6.neigh.default.gc_thresh3=$neigh_thresh3
    log "✓ Optimized IPv6 neighbor table (${neigh_thresh3} max entries)"
    
    # =================================================================
    # Connection Tracking Optimizations
    # =================================================================
    log "Optimizing connection tracking..."
    
    # Scale connection tracking with memory and CPU
    local conntrack_max=$((TOTAL_MEM_GB * CPU_CORES * 8192))
    
    # Apply caps and minimums
    [[ $conntrack_max -gt 1048576 ]] && conntrack_max=1048576    # Max 1M
    [[ $conntrack_max -lt 65536 ]] && conntrack_max=65536        # Min 64K
    
    sysctl -w net.nf_conntrack_max=$conntrack_max
    log "✓ Set connection tracking max to ${conntrack_max}"
    
    # =================================================================
    # File System Optimizations
    # =================================================================
    log "Optimizing file system limits..."
    
    # File descriptor limits (scale with memory)
    local file_max=$((TOTAL_MEM_GB * 65536))
    [[ $file_max -gt 2097152 ]] && file_max=2097152  # Max 2M
    [[ $file_max -lt 1048576 ]] && file_max=1048576  # Min 1M
    
    sysctl -w fs.file-max=$file_max
    sysctl -w fs.nr_open=$file_max
    log "✓ Set file descriptor limits to ${file_max}"
    
    # =================================================================
    # Performance and Latency Optimizations
    # =================================================================
    log "Applying performance optimizations..."
    
    # Disable ICMP rate limiting for testing
    sysctl -w net.ipv4.icmp_ratelimit=0
    log "✓ Disabled ICMP rate limiting"
    
    # Disable route garbage collection
    sysctl -w net.ipv4.route.gc_thresh=-1
    sysctl -w net.ipv6.route.gc_thresh=-1
    log "✓ Disabled route garbage collection"
    
    # TCP optimizations
    sysctl -w net.ipv4.tcp_congestion_control=bbr 2>/dev/null || sysctl -w net.ipv4.tcp_congestion_control=cubic
    log "✓ Optimized TCP congestion control"
    
    log "Kernel tuning completed successfully!"
}

# Make settings persistent
make_persistent() {
    log "Making settings persistent..."
    
    cat > "$CONFIG_FILE" << EOF
# =============================================================================
# Universal Host Kernel Tuning Configuration
# =============================================================================
# Generated by: $SCRIPT_NAME v$SCRIPT_VERSION
# Created: $(date)
# System: $OS_NAME $OS_VERSION ($KERNEL_VERSION)
# Memory: ${TOTAL_MEM_GB}GB, CPU: ${CPU_CORES} cores
# =============================================================================

# Container and Process Limits
kernel.pty.max = 131072
kernel.pid_max = 4194304

# Network Core
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0

# Network Device Queues
net.core.netdev_max_backlog = 30000
net.core.netdev_budget = 600
net.core.netdev_budget_usecs = 8000

# Socket Buffers
net.core.rmem_default = 262144
net.core.rmem_max = $(sysctl -n net.core.rmem_max)
net.core.wmem_default = 262144
net.core.wmem_max = $(sysctl -n net.core.wmem_max)

# TCP Buffers
net.ipv4.tcp_rmem = $(sysctl -n net.ipv4.tcp_rmem)
net.ipv4.tcp_wmem = $(sysctl -n net.ipv4.tcp_wmem)

# Neighbor Tables
net.ipv4.neigh.default.gc_thresh1 = $(sysctl -n net.ipv4.neigh.default.gc_thresh1)
net.ipv4.neigh.default.gc_thresh2 = $(sysctl -n net.ipv4.neigh.default.gc_thresh2)
net.ipv4.neigh.default.gc_thresh3 = $(sysctl -n net.ipv4.neigh.default.gc_thresh3)
net.ipv6.neigh.default.gc_thresh1 = $(sysctl -n net.ipv6.neigh.default.gc_thresh1)
net.ipv6.neigh.default.gc_thresh2 = $(sysctl -n net.ipv6.neigh.default.gc_thresh2)
net.ipv6.neigh.default.gc_thresh3 = $(sysctl -n net.ipv6.neigh.default.gc_thresh3)

# Connection Tracking
net.nf_conntrack_max = $(sysctl -n net.nf_conntrack_max)

# File System
fs.file-max = $(sysctl -n fs.file-max)
fs.nr_open = $(sysctl -n fs.nr_open)

# Performance
net.ipv4.icmp_ratelimit = 0
net.ipv4.route.gc_thresh = -1
net.ipv6.route.gc_thresh = -1
EOF
    
    log "✓ Settings saved to: $CONFIG_FILE"
    log "✓ Settings will persist across reboots"
}

# Verify applied settings
verify_settings() {
    log "Verifying applied settings..."
    
    local failed=0
    local checks=(
        "net.ipv4.ip_forward:1"
        "kernel.pty.max:131072"
        "net.nf_conntrack_max"
        "fs.file-max"
    )
    
    for check in "${checks[@]}"; do
        local param="${check%:*}"
        local expected="${check#*:}"
        local current=$(sysctl -n "$param" 2>/dev/null || echo "MISSING")
        
        if [[ "$expected" != "" && "$current" != "$expected" ]]; then
            error "Verification failed: $param = $current (expected: $expected)"
            failed=1
        elif [[ "$current" == "MISSING" ]]; then
            warn "Parameter not available: $param"
        else
            log "✓ Verified: $param = $current"
        fi
    done
    
    if [[ $failed -eq 0 ]]; then
        log "✓ All critical settings verified successfully"
        return 0
    else
        error "Some settings verification failed"
        return 1
    fi
}

# Show current settings
show_settings() {
    echo -e "${PURPLE}"
    echo "============================================================================="
    echo "                    Current Kernel Tuning Settings"
    echo "============================================================================="
    echo -e "${NC}"
    
    echo -e "${BLUE}System Information:${NC}"
    echo "  OS: $OS_NAME $OS_VERSION"
    echo "  Kernel: $KERNEL_VERSION"
    echo "  Memory: ${TOTAL_MEM_GB}GB"
    echo "  CPU Cores: $CPU_CORES"
    echo ""
    
    echo -e "${BLUE}Container Limits:${NC}"
    echo "  kernel.pty.max = $(sysctl -n kernel.pty.max 2>/dev/null || echo 'N/A')"
    echo "  kernel.pid_max = $(sysctl -n kernel.pid_max 2>/dev/null || echo 'N/A')"
    echo ""
    
    echo -e "${BLUE}Network Core:${NC}"
    echo "  net.ipv4.ip_forward = $(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 'N/A')"
    echo "  net.core.netdev_max_backlog = $(sysctl -n net.core.netdev_max_backlog 2>/dev/null || echo 'N/A')"
    echo ""
    
    echo -e "${BLUE}Neighbor Tables:${NC}"
    echo "  IPv4 gc_thresh1/2/3 = $(sysctl -n net.ipv4.neigh.default.gc_thresh1 2>/dev/null || echo 'N/A')/$(sysctl -n net.ipv4.neigh.default.gc_thresh2 2>/dev/null || echo 'N/A')/$(sysctl -n net.ipv4.neigh.default.gc_thresh3 2>/dev/null || echo 'N/A')"
    echo ""
    
    echo -e "${BLUE}Connection Tracking:${NC}"
    echo "  net.nf_conntrack_max = $(sysctl -n net.nf_conntrack_max 2>/dev/null || echo 'N/A')"
    echo ""
    
    echo -e "${BLUE}File Limits:${NC}"
    echo "  fs.file-max = $(sysctl -n fs.file-max 2>/dev/null || echo 'N/A')"
    echo ""
}

# Reset to defaults
reset_settings() {
    warn "This will remove the persistent tuning configuration"
    read -p "Are you sure you want to reset? (y/N): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Reset cancelled"
        return 0
    fi
    
    if [[ -f "$CONFIG_FILE" ]]; then
        rm -f "$CONFIG_FILE"
        log "✓ Removed configuration file: $CONFIG_FILE"
    fi
    
    warn "Reboot required to fully restore default settings"
}

# Show usage
show_usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  apply    - Apply kernel tuning optimizations"
    echo "  show     - Show current settings"
    echo "  verify   - Verify applied settings"
    echo "  reset    - Reset to default settings"
    echo "  help     - Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo $0 apply     # Apply all optimizations"
    echo "  sudo $0 show      # Show current settings"
    echo "  sudo $0 verify    # Verify settings"
    echo ""
}

# Main function
main() {
    echo -e "${PURPLE}"
    echo "============================================================================="
    echo "                    $SCRIPT_NAME v$SCRIPT_VERSION"
    echo "============================================================================="
    echo -e "${NC}"
    
    check_root
    detect_system
    
    local command="${1:-help}"
    
    case "$command" in
        "apply")
            backup_current_settings
            apply_kernel_tuning
            make_persistent
            verify_settings
            show_settings
            ;;
        "show")
            show_settings
            ;;
        "verify")
            verify_settings
            ;;
        "reset")
            reset_settings
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            error "Unknown command: $command"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
