#!/usr/bin/env bash
# Test script for setup.sh validation
# This script performs non-destructive tests to validate setup.sh functionality

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="$SCRIPT_DIR/setup.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Logging functions
log_test() {
    echo -e "${YELLOW}[TEST]${NC} $*"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
    ((TESTS_FAILED++))
}

log_info() {
    echo -e "[INFO] $*"
}

# Test functions
test_script_exists() {
    log_test "Checking if setup script exists..."
    if [[ -f "$SETUP_SCRIPT" ]]; then
        log_pass "Setup script found at $SETUP_SCRIPT"
    else
        log_fail "Setup script not found at $SETUP_SCRIPT"
    fi
}

test_script_executable() {
    log_test "Checking if setup script is executable..."
    if [[ -x "$SETUP_SCRIPT" ]]; then
        log_pass "Setup script is executable"
        return 0
    else
        log_fail "Setup script is not executable"
        return 1
    fi
}

test_script_syntax() {
    log_test "Checking script syntax..."
    if bash -n "$SETUP_SCRIPT"; then
        log_pass "Script syntax is valid"
    else
        log_fail "Script syntax is invalid"
    fi
}

test_help_option() {
    log_test "Testing --help option..."
    if output=$(bash "$SETUP_SCRIPT" --help 2>&1); then
        if echo "$output" | grep -q "Network Analysis Tool Setup Script"; then
            log_pass "--help option works correctly"
        else
            log_fail "--help option doesn't show expected content"
        fi
    else
        log_fail "--help option failed"
    fi
}

test_invalid_option() {
    log_test "Testing invalid option handling..."
    if output=$(bash "$SETUP_SCRIPT" --invalid-option 2>&1); then
        log_fail "Script should reject invalid options"
    else
        if echo "$output" | grep -q "Unknown option"; then
            log_pass "Invalid option handling works correctly"
        else
            log_fail "Invalid option error message not found"
        fi
    fi
}

test_root_check() {
    log_test "Testing root privilege check..."
    if [[ $EUID -eq 0 ]]; then
        log_info "Running as root - skipping root check test"
    else
        # Test that script fails when not run as root
        if output=$(bash "$SETUP_SCRIPT" --skip-source-change --skip-docker --skip-clone 2>&1); then
            log_fail "Script should require root privileges"
        else
            if echo "$output" | grep -q "must be run as root"; then
                log_pass "Root privilege check works correctly"
            else
                log_fail "Root privilege error message not found"
            fi
        fi
    fi
}

test_function_definitions() {
    log_test "Checking if required functions are defined..."
    local required_functions=(
        "log_info"
        "log_error" 
        "error_exit"
        "check_root"
        "check_system"
        "backup_config"
        "setup_package_sources"
        "setup_docker"
        "install_tools"
        "configure_docker_crun"
        "clone_project"
        "setup_project_environment"
        "main"
    )
    
    local missing_functions=()
    for func in "${required_functions[@]}"; do
        if ! grep -q "^$func()" "$SETUP_SCRIPT"; then
            missing_functions+=("$func")
        fi
    done
    
    if [[ ${#missing_functions[@]} -eq 0 ]]; then
        log_pass "All required functions are defined"
    else
        log_fail "Missing functions: ${missing_functions[*]}"
    fi
}

test_configuration_variables() {
    log_test "Checking configuration variables..."
    local required_vars=(
        "DEFAULT_SOFT_SOURCE"
        "SOFT_SOURCE"
        "SCRIPT_DIR"
        "LOG_FILE"
        "BACKUP_DIR"
    )
    
    local missing_vars=()
    for var in "${required_vars[@]}"; do
        if ! grep -q "^$var=" "$SETUP_SCRIPT"; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -eq 0 ]]; then
        log_pass "All required configuration variables are defined"
    else
        log_fail "Missing variables: ${missing_vars[*]}"
    fi
}

test_error_handling() {
    log_test "Checking error handling patterns..."
    
    # Check for set -euo pipefail
    if grep -q "set -euo pipefail" "$SETUP_SCRIPT"; then
        log_pass "Strict error handling is enabled (set -euo pipefail)"
    else
        log_fail "Strict error handling not found"
    fi
    
    # Check for error_exit usage
    if grep -q "error_exit" "$SETUP_SCRIPT"; then
        log_pass "Error exit function is used"
    else
        log_fail "Error exit function not found"
    fi
}

test_logging_functionality() {
    log_test "Checking logging functionality..."
    
    local log_functions=("log_info" "log_warn" "log_error" "log_debug")
    local missing_log_funcs=()
    
    for func in "${log_functions[@]}"; do
        if ! grep -q "$func()" "$SETUP_SCRIPT"; then
            missing_log_funcs+=("$func")
        fi
    done
    
    if [[ ${#missing_log_funcs[@]} -eq 0 ]]; then
        log_pass "All logging functions are defined"
    else
        log_fail "Missing logging functions: ${missing_log_funcs[*]}"
    fi
}

test_backup_functionality() {
    log_test "Checking backup functionality..."
    
    if grep -q "backup_config" "$SETUP_SCRIPT" && grep -q "BACKUP_DIR" "$SETUP_SCRIPT"; then
        log_pass "Backup functionality is implemented"
    else
        log_fail "Backup functionality not found"
    fi
}

# Main test execution
main() {
    log_info "Starting setup script validation tests..."
    log_info "Setup script: $SETUP_SCRIPT"
    echo

    # Run all tests (continue even if some fail)
    test_script_exists || true
    test_script_executable || true
    test_script_syntax || true
    test_help_option || true
    test_invalid_option || true
    test_root_check || true
    test_function_definitions || true
    test_configuration_variables || true
    test_error_handling || true
    test_logging_functionality || true
    test_backup_functionality || true
    
    # Summary
    echo
    log_info "Test Summary:"
    log_info "  Passed: $TESTS_PASSED"
    log_info "  Failed: $TESTS_FAILED"
    log_info "  Total:  $((TESTS_PASSED + TESTS_FAILED))"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed!${NC}"
        exit 1
    fi
}

# Execute main function only if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
