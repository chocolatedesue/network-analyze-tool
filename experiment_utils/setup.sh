#!/usr/bin/env bash
# Network Analysis Tool Environment Setup Script
#
# This script sets up a complete environment for network analysis experiments including:
# 1. 换源 (Change package sources)
# 2. 构建 crun 和 安装docker (Build crun and install Docker)
# 3. 将 docker 默认 runtime 切换为 crun (Switch Docker default runtime to crun)
# 4. 安装 containerlab mise (Install containerlab and other tools)
# 5. clone 实验项目 (Clone experiment project)
#
# Requirements: Must be executed as root user
# Usage: sudo bash setup.sh [--source <mirror>] [--skip-source-change] [--skip-docker] [--help]

set -euo pipefail

# ============================================================================
# Configuration and Global Variables
# ============================================================================

# Default configuration
DEFAULT_SOFT_SOURCE="mirrors.pku.edu.cn"
SOFT_SOURCE="${SOFT_SOURCE:-$DEFAULT_SOFT_SOURCE}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/network-tool-setup-$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="/root/network-tool-setup-backup-$(date +%Y%m%d_%H%M%S)"

# Feature flags
SKIP_SOURCE_CHANGE=false
SKIP_DOCKER=false
SKIP_CLONE=false
VERBOSE=false

# ============================================================================
# Utility Functions
# ============================================================================

# Logging functions
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        log "DEBUG" "$@"
    fi
}

# Error handling
error_exit() {
    log_error "$1"
    log_error "Setup failed. Check log file: $LOG_FILE"
    exit 1
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error_exit "This script must be run as root. Use: sudo $0"
    fi
}

# Check system requirements
check_system() {
    log_info "Checking system requirements..."

    # Check OS
    if ! command -v dnf >/dev/null 2>&1; then
        error_exit "This script requires a DNF-based system (RHEL/CentOS/Fedora)"
    fi

    # Check internet connectivity
    if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log_warn "Internet connectivity check failed. Proceeding anyway..."
    fi

    # Check available disk space (minimum 5GB)
    local available_space=$(df / | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 5242880 ]]; then  # 5GB in KB
        log_warn "Low disk space detected. At least 5GB recommended."
    fi

    log_info "System requirements check completed"
}

# Backup existing configuration
backup_config() {
    log_info "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"

    # Backup existing Docker daemon.json if it exists
    if [[ -f /etc/docker/daemon.json ]]; then
        cp /etc/docker/daemon.json "$BACKUP_DIR/daemon.json.bak"
        log_info "Backed up existing Docker daemon.json"
    fi
}

# Show help
show_help() {
    cat << EOF
Network Analysis Tool Setup Script

Usage: $0 [OPTIONS]

OPTIONS:
    --source <mirror>       Set package mirror source (default: $DEFAULT_SOFT_SOURCE)
    --skip-source-change    Skip changing package sources
    --skip-docker          Skip Docker installation and configuration
    --skip-clone           Skip cloning the project repository
    --verbose              Enable verbose logging
    --help                 Show this help message

EXAMPLES:
    $0                                    # Full setup with default settings
    $0 --source mirrors.tuna.tsinghua.edu.cn  # Use different mirror
    $0 --skip-docker                     # Skip Docker setup
    $0 --verbose                         # Enable verbose output

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --source)
                SOFT_SOURCE="$2"
                shift 2
                ;;
            --skip-source-change)
                SKIP_SOURCE_CHANGE=true
                shift
                ;;
            --skip-docker)
                SKIP_DOCKER=true
                shift
                ;;
            --skip-clone)
                SKIP_CLONE=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1. Use --help for usage information."
                ;;
        esac
    done
}

# ============================================================================
# Setup Functions
# ============================================================================

# Change package sources
setup_package_sources() {
    if [[ "$SKIP_SOURCE_CHANGE" == "true" ]]; then
        log_info "Skipping package source change (--skip-source-change specified)"
        return 0
    fi

    log_info "Setting up package sources using mirror: $SOFT_SOURCE"

    if ! bash <(curl -sSL https://linuxmirrors.cn/main.sh) \
        --source "$SOFT_SOURCE" \
        --protocol http \
        --use-intranet-source false \
        --install-epel true \
        --backup true \
        --upgrade-software false \
        --clean-cache true \
        --ignore-backup-tips; then
        error_exit "Failed to setup package sources"
    fi

    log_info "Package sources setup completed"
}

# Install Docker
setup_docker() {
    if [[ "$SKIP_DOCKER" == "true" ]]; then
        log_info "Skipping Docker setup (--skip-docker specified)"
        return 0
    fi

    log_info "Installing Docker with crun runtime..."

    # Install Docker
    if ! bash <(curl -sSL https://linuxmirrors.cn/docker.sh) \
        --source "$SOFT_SOURCE/docker-ce" \
        --install-latest true \
        --source-registry registry.cn-beijing.aliyuncs.com \
        --protocol http; then
        error_exit "Failed to install Docker"
    fi

    log_info "Docker installation completed"
}

# Install additional tools
install_tools() {
    log_info "Installing additional tools (containerlab, fish, uv, crun, jq)..."

    # Add netdevops repository
    if ! dnf config-manager -y --add-repo "https://netdevops.fury.site/yum/"; then
        error_exit "Failed to add netdevops repository"
    fi

    # Disable GPG check for netdevops repo
    echo "gpgcheck=0" | tee -a /etc/yum.repos.d/netdevops.fury.site_yum_.repo

    # Install packages
    if ! dnf install containerlab fish uv crun jq -y; then
        error_exit "Failed to install required tools"
    fi

    log_info "Additional tools installation completed"
}

# Configure Docker to use crun
configure_docker_crun() {
    if [[ "$SKIP_DOCKER" == "true" ]]; then
        log_info "Skipping Docker crun configuration (--skip-docker specified)"
        return 0
    fi

    log_info "Configuring Docker to use crun as default runtime..."

    # Verify crun is installed
    local crun_path
    if ! crun_path=$(which crun); then
        error_exit "crun not found in PATH"
    fi

    log_debug "Found crun at: $crun_path"

    # Create Docker daemon configuration
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json << EOF
{
  "default-runtime": "crun",
  "runtimes": {
    "crun": {
      "path": "$crun_path"
    }
  },
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

    # Restart Docker service
    if ! systemctl restart docker; then
        error_exit "Failed to restart Docker service"
    fi

    # Verify Docker is running
    if ! systemctl is-active --quiet docker; then
        error_exit "Docker service is not running after restart"
    fi

    # Test Docker with crun
    if ! docker run --rm hello-world >/dev/null 2>&1; then
        log_warn "Docker test run failed, but continuing setup..."
    else
        log_info "Docker with crun runtime verified successfully"
    fi

    log_info "Docker crun configuration completed"
}

# Clone project repository
clone_project() {
    if [[ "$SKIP_CLONE" == "true" ]]; then
        log_info "Skipping project clone (--skip-clone specified)"
        return 0
    fi

    log_info "Cloning network-analyze-tool project..."

    local repo_url="https://xget.xi-xu.me/gh/chocolatedesue/network-analyze-tool.git"
    local target_dir="network-analyze-tool"

    # Remove existing directory if it exists
    if [[ -d "$target_dir" ]]; then
        log_warn "Directory $target_dir already exists, removing..."
        rm -rf "$target_dir"
    fi

    # Clone repository
    if ! git clone "$repo_url" --depth=1 "$target_dir"; then
        error_exit "Failed to clone project repository"
    fi

    log_info "Project repository cloned successfully"
}

# Setup project environment
setup_project_environment() {
    if [[ "$SKIP_CLONE" == "true" ]]; then
        log_info "Skipping project environment setup (--skip-clone specified)"
        return 0
    fi

    log_info "Setting up project environment..."

    local project_dir="network-analyze-tool"

    if [[ ! -d "$project_dir" ]]; then
        error_exit "Project directory $project_dir not found"
    fi

    cd "$project_dir"

    # Install Python dependencies
    if ! uv sync; then
        error_exit "Failed to sync Python dependencies with uv"
    fi

    # Run additional setup script
    local setup_script="experiment_utils/setup/tn2.sh"
    if [[ -f "$setup_script" ]]; then
        log_info "Running additional setup script: $setup_script"
        if ! bash "$setup_script"; then
            log_warn "Additional setup script failed, but continuing..."
        fi
    else
        log_warn "Additional setup script not found: $setup_script"
    fi

    log_info "Project environment setup completed"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    # Initialize
    parse_args "$@"

    log_info "Starting Network Analysis Tool setup..."
    log_info "Log file: $LOG_FILE"
    log_info "Backup directory: $BACKUP_DIR"

    # Pre-flight checks
    check_root
    check_system
    backup_config

    # Execute setup steps
    setup_package_sources
    setup_docker
    install_tools
    configure_docker_crun
    clone_project
    setup_project_environment

    # Success message
    log_info "Setup completed successfully!"
    log_info "Summary:"
    log_info "  - Package sources: $([ "$SKIP_SOURCE_CHANGE" == "true" ] && echo "skipped" || echo "configured ($SOFT_SOURCE)")"
    log_info "  - Docker: $([ "$SKIP_DOCKER" == "true" ] && echo "skipped" || echo "installed with crun runtime")"
    log_info "  - Tools: containerlab, fish, uv, crun, jq installed"
    log_info "  - Project: $([ "$SKIP_CLONE" == "true" ] && echo "skipped" || echo "cloned and configured")"
    log_info "  - Log file: $LOG_FILE"
    log_info "  - Backup directory: $BACKUP_DIR"

    if [[ "$SKIP_CLONE" == "false" ]]; then
        log_info ""
        log_info "Next steps:"
        log_info "  cd network-analyze-tool"
        log_info "  # Start using the network analysis tools"
    fi
}

# Execute main function with all arguments
main "$@"

