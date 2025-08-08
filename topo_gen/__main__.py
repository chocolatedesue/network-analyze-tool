#!/usr/bin/env python3
"""
Entry point for running topo_gen as a module
This allows running: python -m topo_gen
"""

from .cli import app

if __name__ == "__main__":
    app()
