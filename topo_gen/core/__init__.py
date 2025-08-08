"""
核心模块初始化
导出主要的类型和模型
"""

from .types import (
    Coordinate, Direction, TopologyType, NodeType, ProtocolType,
    RouterName, InterfaceName, IPv6Address, ASNumber, RouterID,
    NeighborMap, Link
)

from .models import (
    TopologyConfig, RouterInfo, LinkInfo, NetworkConfig,
    OSPFConfig, BGPConfig, BFDConfig, SpecialTopologyConfig,
    SystemRequirements, GenerationResult
)

__all__ = [
    # 类型
    'Coordinate', 'Direction', 'TopologyType', 'NodeType', 'ProtocolType',
    'RouterName', 'InterfaceName', 'IPv6Address', 'ASNumber', 'RouterID',
    'NeighborMap', 'Link',

    # 模型
    'TopologyConfig', 'RouterInfo', 'LinkInfo', 'NetworkConfig',
    'OSPFConfig', 'BGPConfig', 'BFDConfig', 'SpecialTopologyConfig',
    'SystemRequirements', 'GenerationResult'
]
