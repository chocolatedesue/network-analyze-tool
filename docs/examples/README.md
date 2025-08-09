# Examples and Demonstrations

This directory contains example code and demonstrations for the topo_gen package.

## Files

### type_validation.py
A comprehensive demonstration of the Pydantic type system used in topo_gen. This file showcases:

- Coordinate validation and functionality
- Direction enum features
- IPv6 address helpers
- Link validation
- Router information models
- Topology configuration examples

**Usage:**
```bash
cd docs/examples
uv run python type_validation.py
```

This will run all type system validations and demonstrations, showing how the various Pydantic models work together to provide robust type checking and validation for network topology generation.

## Purpose

These examples serve as:
- Documentation of the type system capabilities
- Testing ground for new features
- Reference implementations for developers
- Educational material for understanding the codebase structure

The examples are separate from the production code to maintain clear boundaries between demonstration/educational content and the core functionality.
