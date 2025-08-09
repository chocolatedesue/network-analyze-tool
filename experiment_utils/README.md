# Network Analysis Tool - Experiment Utils

This directory contains utilities for setting up and managing network analysis experiments.

## Setup Script (`setup.sh`)

The main setup script automates the complete environment setup for network analysis experiments.

### Features

- **Comprehensive Environment Setup**: Configures package sources, installs Docker with crun runtime, and sets up all required tools
- **Error Handling**: Robust error handling with detailed logging and rollback capabilities
- **Modular Design**: Skip specific setup steps with command-line flags
- **Backup & Recovery**: Automatic backup of existing configurations
- **Verbose Logging**: Detailed logging with timestamps for troubleshooting
- **System Validation**: Pre-flight checks for system requirements and connectivity

### Requirements

- **Operating System**: RHEL/CentOS/Fedora (DNF-based systems)
- **Privileges**: Must be run as root user
- **Disk Space**: Minimum 5GB available space recommended
- **Network**: Internet connectivity required for package downloads

### Usage

#### Basic Usage
```bash
sudo bash experiment_utils/setup.sh
```

#### Advanced Usage
```bash
# Use different package mirror
sudo bash experiment_utils/setup.sh --source mirrors.tuna.tsinghua.edu.cn

# Skip Docker installation (if already installed)
sudo bash experiment_utils/setup.sh --skip-docker

# Skip changing package sources (use existing configuration)
sudo bash experiment_utils/setup.sh --skip-source-change

# Skip project cloning (setup environment only)
sudo bash experiment_utils/setup.sh --skip-clone

# Enable verbose logging
sudo bash experiment_utils/setup.sh --verbose

# Combine multiple options
sudo bash experiment_utils/setup.sh --skip-docker --verbose --source mirrors.ustc.edu.cn
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--source <mirror>` | Set package mirror source | `mirrors.pku.edu.cn` |
| `--skip-source-change` | Skip changing package sources | `false` |
| `--skip-docker` | Skip Docker installation and configuration | `false` |
| `--skip-clone` | Skip cloning the project repository | `false` |
| `--verbose` | Enable verbose logging | `false` |
| `--help` | Show help message | - |

### What Gets Installed

1. **Package Sources**: Configures optimized package mirrors for faster downloads
2. **Docker**: Latest Docker CE with optimized configuration
3. **Container Runtime**: crun as the default Docker runtime for better performance
4. **Network Tools**: 
   - `containerlab` - Network topology simulation
   - `fish` - Enhanced shell
   - `uv` - Fast Python package manager
   - `crun` - High-performance container runtime
   - `jq` - JSON processor
5. **Project Setup**: Clones and configures the network-analyze-tool project

### Logging and Backup

- **Log Files**: Detailed logs are saved to `/tmp/network-tool-setup-YYYYMMDD_HHMMSS.log`
- **Backup Directory**: Configuration backups are stored in `/root/network-tool-setup-backup-YYYYMMDD_HHMMSS/`
- **Recovery**: Use backup files to restore previous configurations if needed

### Troubleshooting

#### Common Issues

1. **Permission Denied**
   ```bash
   # Solution: Run as root
   sudo bash experiment_utils/setup.sh
   ```

2. **Network Connectivity Issues**
   ```bash
   # Check internet connectivity
   ping -c 3 8.8.8.8
   
   # Try different mirror source
   sudo bash experiment_utils/setup.sh --source mirrors.ustc.edu.cn
   ```

3. **Docker Service Issues**
   ```bash
   # Check Docker status
   systemctl status docker
   
   # Restart Docker if needed
   sudo systemctl restart docker
   ```

4. **Low Disk Space**
   ```bash
   # Check available space
   df -h /
   
   # Clean up if needed
   sudo dnf clean all
   ```

#### Debug Mode

Enable verbose logging for detailed troubleshooting:
```bash
sudo bash experiment_utils/setup.sh --verbose
```

Check the log file for detailed error information:
```bash
tail -f /tmp/network-tool-setup-*.log
```

### Recovery and Rollback

If something goes wrong, you can restore previous configurations:

```bash
# Find your backup directory
ls -la /root/network-tool-setup-backup-*/

# Restore Docker configuration (example)
sudo cp /root/network-tool-setup-backup-*/daemon.json.bak /etc/docker/daemon.json
sudo systemctl restart docker
```

### Performance Optimizations

The setup script includes several performance optimizations:

1. **Docker Configuration**: Optimized logging and runtime settings
2. **crun Runtime**: Faster container startup and lower resource usage
3. **Package Mirrors**: Uses geographically optimized package sources
4. **System Tuning**: Applies network and system optimizations via `tn2.sh`

### Security Considerations

- **Root Privileges**: Required for system-level configuration changes
- **Network Downloads**: Downloads packages and scripts from trusted sources
- **Configuration Backup**: Automatically backs up existing configurations
- **GPG Verification**: Disabled for netdevops repository (required for containerlab)

## Other Utilities

- `auto.py` - Automation utilities for experiment execution
- `clear_logs.py` - Log cleanup utilities
- `execute_in_batches.py` - Batch execution management
- `inject.py` - Network injection utilities
- `utils.py` - Common utility functions

## Setup Directory

The `setup/` directory contains additional configuration scripts:

- `tn2.sh` - Network tuning and optimization script
- `dp.sh` - Data plane configuration
- `tunning.sh` - Performance tuning utilities

For more information about these scripts, see their individual documentation.
