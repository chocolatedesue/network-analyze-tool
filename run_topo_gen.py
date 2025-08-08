#!/usr/bin/env python3
"""
Convenience script to run topo_gen CLI
Usage: python run_topo_gen.py [args...]
"""

import sys
import subprocess

if __name__ == "__main__":
    # Run the topo_gen module with uv
    cmd = ["uv", "run", "-m", "topo_gen"] + sys.argv[1:]
    subprocess.run(cmd)
