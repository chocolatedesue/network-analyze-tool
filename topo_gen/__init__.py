"""
Topology Generator Package

A modern Python package for generating network topologies with support for
various topology types including grid, torus, and custom configurations.
"""

__version__ = "0.1.0"
__author__ = "Network Analyze Tool"

# Import main components for easy access
from .core.types import TopologyType, Coordinate
from .core.models import TopologyConfig, NetworkConfig

__all__ = [
    "TopologyType",
    "Coordinate", 
    "TopologyConfig",
    "NetworkConfig",
]
