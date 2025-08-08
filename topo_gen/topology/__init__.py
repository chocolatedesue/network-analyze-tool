"""
拓扑模块初始化
导出拓扑生成器和工具函数
"""

from .base import (
    BaseTopology, TopologyGenerator, TopologyFactory,
    NeighborMapper, NodeTypeClassifier, TopologyValidator
)

from .grid import (
    GridTopology, create_grid_topology, get_grid_neighbors,
    get_grid_node_type, calculate_grid_stats, validate_grid_topology
)

from .torus import (
    TorusTopology, create_torus_topology, get_torus_neighbors,
    get_torus_node_type, calculate_torus_stats, validate_torus_topology
)

from .special import (
    SpecialTopology, create_special_topology, create_dm6_6_sample,
    get_special_connected_nodes, filter_routers_for_special_topology,
    calculate_special_stats, validate_special_topology
)

__all__ = [
    # 基础类
    'BaseTopology', 'TopologyGenerator', 'TopologyFactory',
    'NeighborMapper', 'NodeTypeClassifier', 'TopologyValidator',
    
    # Grid拓扑
    'GridTopology', 'create_grid_topology', 'get_grid_neighbors',
    'get_grid_node_type', 'calculate_grid_stats', 'validate_grid_topology',
    
    # Torus拓扑
    'TorusTopology', 'create_torus_topology', 'get_torus_neighbors',
    'get_torus_node_type', 'calculate_torus_stats', 'validate_torus_topology',

    # Special拓扑
    'SpecialTopology', 'create_special_topology', 'create_dm6_6_sample',
    'get_special_connected_nodes', 'filter_routers_for_special_topology',
    'calculate_special_stats', 'validate_special_topology'
]
