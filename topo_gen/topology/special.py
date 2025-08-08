"""
Special拓扑实现
支持特殊拓扑配置，包括网关节点、特殊连接等
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple
from dataclasses import dataclass

from ..core.types import Coordinate, Direction, TopologyType, NodeType
from ..core.models import SpecialTopologyConfig
from .base import BaseTopology


@dataclass
class SpecialTopology(BaseTopology):
    """Special拓扑实现"""
    
    def __init__(self, topology_type):
        super().__init__(topology_type)
    
    def get_neighbors(self, coord: Coordinate, size: int, special_config: SpecialTopologyConfig) -> Dict[Direction, Coordinate]:
        """获取Special拓扑中的邻居节点"""
        neighbors = {}

        # 1. 首先获取基础拓扑的邻居（过滤跨区域连接）
        if special_config.include_base_connections:
            if special_config.base_topology == TopologyType.TORUS:
                neighbors = self._get_torus_neighbors(coord, size)
            else:  # GRID - 使用过滤后的邻居
                neighbors = get_filtered_grid_neighbors(coord, size)

        # 2. 添加特殊连接
        # 内部桥接连接
        for edge in special_config.internal_bridge_edges:
            if edge[0] == coord:
                # 找一个可用的方向
                for direction in Direction:
                    if direction not in neighbors:
                        neighbors[direction] = edge[1]
                        break
            elif edge[1] == coord:
                # 找一个可用的方向
                for direction in Direction:
                    if direction not in neighbors:
                        neighbors[direction] = edge[0]
                        break

        # Torus桥接连接（为gateway节点提供额外接口）
        for edge in special_config.torus_bridge_edges:
            if edge[0] == coord:
                # 找一个可用的方向
                for direction in Direction:
                    if direction not in neighbors:
                        neighbors[direction] = edge[1]
                        break
            elif edge[1] == coord:
                # 找一个可用的方向
                for direction in Direction:
                    if direction not in neighbors:
                        neighbors[direction] = edge[0]
                        break

        return neighbors
    
    def _get_grid_neighbors(self, coord: Coordinate, size: int) -> Dict[Direction, Coordinate]:
        """获取Grid拓扑的邻居"""
        neighbors = {}
        row, col = coord.row, coord.col
        
        if row > 0:
            neighbors[Direction.NORTH] = Coordinate(row=row - 1, col=col)
        if row < size - 1:
            neighbors[Direction.SOUTH] = Coordinate(row=row + 1, col=col)
        if col > 0:
            neighbors[Direction.WEST] = Coordinate(row=row, col=col - 1)
        if col < size - 1:
            neighbors[Direction.EAST] = Coordinate(row=row, col=col + 1)
        
        return neighbors
    
    def _get_torus_neighbors(self, coord: Coordinate, size: int) -> Dict[Direction, Coordinate]:
        """获取Torus拓扑的邻居"""
        row, col = coord.row, coord.col
        return {
            Direction.NORTH: Coordinate(row=(row - 1 + size) % size, col=col),
            Direction.SOUTH: Coordinate(row=(row + 1) % size, col=col),
            Direction.WEST: Coordinate(row=row, col=(col - 1 + size) % size),
            Direction.EAST: Coordinate(row=row, col=(col + 1) % size)
        }
    
    def get_node_type(self, coord: Coordinate, size: int, special_config: SpecialTopologyConfig) -> NodeType:
        """获取Special节点类型"""
        if coord == special_config.source_node:
            return NodeType.SOURCE
        elif coord == special_config.dest_node:
            return NodeType.DESTINATION
        elif coord in special_config.gateway_nodes:
            return NodeType.GATEWAY
        else:
            return NodeType.INTERNAL
    
    def calculate_total_links(self, size: int, special_config: SpecialTopologyConfig) -> int:
        """计算Special拓扑的总链路数"""
        total_links = 0
        
        # 基础拓扑链路
        if special_config.include_base_connections:
            if special_config.base_topology == TopologyType.TORUS:
                total_links += 2 * size * size  # Torus: 每个节点4条边
            else:  # GRID
                total_links += 2 * size * (size - 1)  # Grid: 水平+垂直链路
        
        # 特殊连接链路
        total_links += len(special_config.internal_bridge_edges)
        # 注意：torus_bridge_edges不在ContainerLab中创建
        
        return total_links


def get_subregion_for_coord(coord: Coordinate) -> int:
    """获取坐标所属的子区域编号 (0-3)"""
    # 6x6网格分为4个3x3子区域
    # 区域0: (0,0)-(2,2), 区域1: (0,3)-(2,5)
    # 区域2: (3,0)-(5,2), 区域3: (3,3)-(5,5)
    region_row = 0 if coord.row < 3 else 1
    region_col = 0 if coord.col < 3 else 1
    return region_row * 2 + region_col


def is_cross_region_connection(coord1: Coordinate, coord2: Coordinate) -> bool:
    """判断两个坐标之间的连接是否跨越子区域边界"""
    return get_subregion_for_coord(coord1) != get_subregion_for_coord(coord2)


def get_filtered_grid_neighbors(coord: Coordinate, size: int) -> Dict[Direction, Coordinate]:
    """获取过滤后的Grid邻居（移除跨区域连接）"""
    neighbors = {}
    row, col = coord.row, coord.col

    # 检查四个方向的邻居
    potential_neighbors = [
        (Direction.NORTH, Coordinate(row=row - 1, col=col)) if row > 0 else None,
        (Direction.SOUTH, Coordinate(row=row + 1, col=col)) if row < size - 1 else None,
        (Direction.WEST, Coordinate(row=row, col=col - 1)) if col > 0 else None,
        (Direction.EAST, Coordinate(row=row, col=col + 1)) if col < size - 1 else None,
    ]

    for item in potential_neighbors:
        if item is None:
            continue
        direction, neighbor_coord = item

        # 只保留同一子区域内的连接
        if not is_cross_region_connection(coord, neighbor_coord):
            neighbors[direction] = neighbor_coord

    return neighbors


def create_dm6_6_sample() -> SpecialTopologyConfig:
    """创建dm6_6_sample特殊拓扑配置"""
    # 源节点和目标节点
    source_node = Coordinate(row=1, col=4)
    dest_node = Coordinate(row=4, col=1)

    # 内部桥接连接（在ContainerLab中创建的物理连接）
    internal_bridge_edges = [
        (Coordinate(row=1, col=2), Coordinate(row=1, col=3)),
        (Coordinate(row=4, col=2), Coordinate(row=4, col=3)),
        (Coordinate(row=2, col=1), Coordinate(row=3, col=1)),
        (Coordinate(row=2, col=4), Coordinate(row=3, col=4)),
    ]

    # Torus桥接连接（只在路由配置中体现，不在ContainerLab中创建）
    torus_bridge_edges = [
        (Coordinate(row=0, col=1), Coordinate(row=5, col=1)),
        (Coordinate(row=0, col=4), Coordinate(row=5, col=4)),
        (Coordinate(row=1, col=0), Coordinate(row=1, col=5)),
        (Coordinate(row=4, col=0), Coordinate(row=4, col=5)),
    ]

    # 16个Gateway节点（根据dm6_6_sample的正确定义）
    gateway_nodes = {
        Coordinate(row=0, col=1), Coordinate(row=0, col=4), Coordinate(row=1, col=0), Coordinate(row=1, col=2),
        Coordinate(row=1, col=3), Coordinate(row=1, col=5), Coordinate(row=2, col=1), Coordinate(row=2, col=4),
        Coordinate(row=3, col=1), Coordinate(row=3, col=4), Coordinate(row=4, col=0), Coordinate(row=4, col=2),
        Coordinate(row=4, col=3), Coordinate(row=4, col=5), Coordinate(row=5, col=1), Coordinate(row=5, col=4)
    }

    return SpecialTopologyConfig(
        source_node=source_node,
        dest_node=dest_node,
        internal_bridge_edges=internal_bridge_edges,
        torus_bridge_edges=torus_bridge_edges,
        gateway_nodes=gateway_nodes,
        base_topology=TopologyType.GRID,
        include_base_connections=True
    )


def get_special_connected_nodes(special_config: SpecialTopologyConfig) -> Set[Coordinate]:
    """获取特殊拓扑中有连接的节点"""
    connected_nodes = set()
    
    # 添加源节点和目标节点
    connected_nodes.add(special_config.source_node)
    connected_nodes.add(special_config.dest_node)
    
    # 添加所有网关节点
    connected_nodes.update(special_config.gateway_nodes)
    
    # 如果包含基础连接，添加所有6x6网格节点
    if special_config.include_base_connections:
        for row in range(6):
            for col in range(6):
                connected_nodes.add(Coordinate(row, col))
    
    # 添加桥接连接涉及的节点
    for edge in special_config.internal_bridge_edges + special_config.torus_bridge_edges:
        connected_nodes.update(edge)
    
    return connected_nodes


def filter_routers_for_special_topology(
    routers: List, 
    special_config: SpecialTopologyConfig
) -> List:
    """过滤出特殊拓扑中需要的路由器"""
    connected_nodes = get_special_connected_nodes(special_config)
    
    filtered_routers = []
    for router in routers:
        if router.coordinate in connected_nodes:
            filtered_routers.append(router)
    
    return filtered_routers


def validate_special_topology(special_config: SpecialTopologyConfig, size: int) -> bool:
    """验证特殊拓扑配置的有效性"""
    # 检查源节点和目标节点是否在网格范围内
    if not (0 <= special_config.source_node.row < size and 0 <= special_config.source_node.col < size):
        return False
    
    if not (0 <= special_config.dest_node.row < size and 0 <= special_config.dest_node.col < size):
        return False
    
    # 检查所有桥接连接的节点是否在网格范围内
    for edge in special_config.internal_bridge_edges + special_config.torus_bridge_edges:
        for coord in edge:
            if not (0 <= coord.row < size and 0 <= coord.col < size):
                return False
    
    # 对于dm6_6_sample，固定为6x6网格，无需额外验证子区域
    
    return True


# 工厂函数
def create_special_topology(special_config: SpecialTopologyConfig) -> SpecialTopology:
    """创建特殊拓扑"""
    return SpecialTopology(TopologyType.SPECIAL)


# 统计函数
def calculate_special_stats(size: int, special_config: SpecialTopologyConfig) -> Dict[str, int]:
    """计算特殊拓扑统计信息"""
    topology = create_special_topology(special_config)
    connected_nodes = get_special_connected_nodes(special_config)
    
    return {
        "total_nodes": len(connected_nodes),
        "total_links": topology.calculate_total_links(size, special_config),
        "gateway_nodes": len(special_config.gateway_nodes),
        "internal_bridges": len(special_config.internal_bridge_edges),
        "torus_bridges": len(special_config.torus_bridge_edges)
    }
