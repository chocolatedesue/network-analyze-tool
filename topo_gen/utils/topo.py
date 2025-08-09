from __future__ import annotations

from typing import Any


def get_topology_type_str(topology_type: Any) -> str:
    """Return normalized topology type as lowercase string.
    Accepts enum-like objects (with .value) or plain strings.
    """
    if hasattr(topology_type, "value"):
        return str(topology_type.value)
    return str(topology_type).lower()

