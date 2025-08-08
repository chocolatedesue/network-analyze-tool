"""
Torus拓扑实现
环形网格拓扑，边界节点环绕连接
"""

from __future__ import annotations

from typing import Dict, List, Set, Optional
from functools import lru_cache

from ..core.types import Coordinate, Direction, NodeType, NeighborMap
from ..utils.functional import pipe, memoize
from .base import (
    BaseTopology, TopologyFactory, NeighborMapper, NodeTypeClassifier,
    get_torus_neighbor_in_direction, calculate_direction
)

class TorusTopology(BaseTopology):
    """Torus拓扑实现"""
    
    def __init__(self, topology_type):
        super().__init__(topology_type)
    
    @memoize
    def get_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取Torus拓扑中的邻居节点
        
        Torus拓扑中，每个节点都与上下左右4个方向的节点连接
        边界节点通过环绕连接到对面的节点
        """
        neighbors = {}
        
        for direction in Direction:
            neighbor_coord = get_torus_neighbor_in_direction(coord, direction, size)
            neighbors[direction] = neighbor_coord
        
        return neighbors
    
    def get_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取Torus节点类型
        
        在Torus拓扑中，所有节点都是内部节点，因为没有真正的边界
        """
        return NodeTypeClassifier.classify_torus_node(coord, size)
    
    def calculate_total_links(self, size: int) -> int:
        """计算Torus拓扑的总链路数
        
        公式: 2 * size * size
        每个节点都有4个邻居，总度数为4 * size^2
        每条边被计算两次，所以链路数为 2 * size^2
        """
        return 2 * size * size
    
    @lru_cache(maxsize=128)
    def get_neighbor_count(self, coord: Coordinate, size: int) -> int:
        """获取指定坐标的邻居数量（Torus中总是4）"""
        return 4
    
    def get_nodes_by_type(self, size: int) -> Dict[NodeType, Set[Coordinate]]:
        """按类型分组获取所有节点"""
        all_coords = set(self.get_all_coordinates(size))
        
        return {
            NodeType.CORNER: set(),
            NodeType.EDGE: set(),
            NodeType.INTERNAL: all_coords,  # Torus中所有节点都是内部节点
            NodeType.GATEWAY: set(),
            NodeType.SOURCE: set(),
            NodeType.DESTINATION: set()
        }
    
    def get_connectivity_stats(self, size: int) -> Dict[str, int]:
        """获取连通性统计信息"""
        return {
            'total_nodes': size * size,
            'total_links': self.calculate_total_links(size),
            'corner_nodes': 0,
            'edge_nodes': 0,
            'internal_nodes': size * size,
            'avg_degree': 4.0,  # Torus中每个节点度数都是4
            'max_degree': 4,
            'min_degree': 4,
        }
    
    def is_connected(self, size: int) -> bool:
        """检查拓扑是否连通"""
        # Torus拓扑在size >= 1时总是连通的
        return size >= 1
    
    def get_diameter(self, size: int) -> int:
        """获取网络直径"""
        # Torus拓扑的直径是 floor(size/2) * 2
        return (size // 2) * 2
    
    def get_shortest_path_length(self, coord1: Coordinate, coord2: Coordinate, size: int) -> int:
        """计算两点间的最短路径长度（Torus距离）"""
        row_dist = min(
            abs(coord1.row - coord2.row),
            size - abs(coord1.row - coord2.row)
        )
        col_dist = min(
            abs(coord1.col - coord2.col),
            size - abs(coord1.col - coord2.col)
        )
        return row_dist + col_dist
    
    def get_torus_distance(self, coord1: Coordinate, coord2: Coordinate, size: int) -> tuple[int, int]:
        """获取Torus拓扑中两点的距离分量"""
        def torus_distance_1d(a: int, b: int, size: int) -> int:
            return min(abs(a - b), size - abs(a - b))
        
        row_dist = torus_distance_1d(coord1.row, coord2.row, size)
        col_dist = torus_distance_1d(coord1.col, coord2.col, size)
        
        return row_dist, col_dist
    
    def get_wrap_around_links(self, size: int) -> List[tuple[Coordinate, Coordinate]]:
        """获取所有环绕链路"""
        wrap_links = []
        
        # 水平环绕链路（左右边界连接）
        for row in range(size):
            coord1 = Coordinate(row=row, col=0)
            coord2 = Coordinate(row=row, col=size - 1)
            wrap_links.append((coord1, coord2))

        # 垂直环绕链路（上下边界连接）
        for col in range(size):
            coord1 = Coordinate(row=0, col=col)
            coord2 = Coordinate(row=size - 1, col=col)
            wrap_links.append((coord1, coord2))
        
        return wrap_links
    
    def get_regular_links(self, size: int) -> List[tuple[Coordinate, Coordinate]]:
        """获取所有常规链路（非环绕）"""
        regular_links = []
        
        # 水平常规链路
        for row in range(size):
            for col in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row, col=col + 1)
                regular_links.append((coord1, coord2))

        # 垂直常规链路
        for col in range(size):
            for row in range(size - 1):
                coord1 = Coordinate(row=row, col=col)
                coord2 = Coordinate(row=row + 1, col=col)
                regular_links.append((coord1, coord2))
        
        return regular_links
    
    def is_wrap_around_link(self, coord1: Coordinate, coord2: Coordinate, size: int) -> bool:
        """判断是否为环绕链路"""
        # 水平环绕
        if (coord1.row == coord2.row and 
            abs(coord1.col - coord2.col) == size - 1):
            return True
        
        # 垂直环绕
        if (coord1.col == coord2.col and 
            abs(coord1.row - coord2.row) == size - 1):
            return True
        
        return False
    
    def get_symmetry_groups(self, size: int) -> List[Set[Coordinate]]:
        """获取对称性分组"""
        # Torus拓扑具有平移对称性
        # 这里简化实现，返回按距离原点的Torus距离分组
        groups = {}
        origin = Coordinate(row=0, col=0)
        
        for coord in self.get_all_coordinates(size):
            distance = self.get_shortest_path_length(origin, coord, size)
            if distance not in groups:
                groups[distance] = set()
            groups[distance].add(coord)
        
        return list(groups.values())
    
    def get_routing_table(self, source: Coordinate, size: int) -> Dict[Coordinate, List[Direction]]:
        """获取从源节点到所有其他节点的最短路径方向"""
        routing_table = {}
        
        for target in self.get_all_coordinates(size):
            if source == target:
                routing_table[target] = []
                continue
            
            directions = []
            
            # 计算行方向
            row_diff = target.row - source.row
            if row_diff != 0:
                if abs(row_diff) <= size // 2:
                    # 直接路径更短
                    directions.append(Direction.SOUTH if row_diff > 0 else Direction.NORTH)
                else:
                    # 环绕路径更短
                    directions.append(Direction.NORTH if row_diff > 0 else Direction.SOUTH)
            
            # 计算列方向
            col_diff = target.col - source.col
            if col_diff != 0:
                if abs(col_diff) <= size // 2:
                    # 直接路径更短
                    directions.append(Direction.EAST if col_diff > 0 else Direction.WEST)
                else:
                    # 环绕路径更短
                    directions.append(Direction.WEST if col_diff > 0 else Direction.EAST)
            
            routing_table[target] = directions
        
        return routing_table
    
    def validate_torus_properties(self, size: int) -> List[str]:
        """验证Torus拓扑的属性"""
        errors = []
        
        # 验证每个节点都有4个邻居
        for coord in self.get_all_coordinates(size):
            neighbor_count = len(self.get_neighbors(coord, size))
            if neighbor_count != 4:
                errors.append(f"节点{coord}的邻居数量不是4: {neighbor_count}")
        
        # 验证链路数量
        expected_links = self.calculate_total_links(size)
        actual_links = 0
        for coord in self.get_all_coordinates(size):
            actual_links += len(self.get_neighbors(coord, size))
        actual_links //= 2  # 每条链路被计算了两次
        
        if actual_links != expected_links:
            errors.append(f"链路数量不匹配: 期望{expected_links}, 实际{actual_links}")
        
        # 验证对称性
        stats = self.get_connectivity_stats(size)
        if stats['min_degree'] != stats['max_degree']:
            errors.append("Torus拓扑应该具有均匀的度数分布")
        
        return errors

# 注册Torus拓扑
TopologyFactory.register('torus', TorusTopology)

# 导出Torus拓扑相关的工具函数
def create_torus_topology() -> TorusTopology:
    """创建Torus拓扑实例"""
    return TorusTopology('torus')

def get_torus_neighbors(size: int):
    """获取Torus邻居计算函数"""
    topology = create_torus_topology()
    return lambda coord: topology.get_neighbors(coord, size)

def get_torus_node_type(size: int):
    """获取Torus节点类型判断函数"""
    topology = create_torus_topology()
    return lambda coord: topology.get_node_type(coord, size)

def calculate_torus_stats(size: int) -> Dict[str, int]:
    """计算Torus拓扑统计信息"""
    topology = create_torus_topology()
    return topology.get_connectivity_stats(size)

def validate_torus_topology(size: int) -> List[str]:
    """验证Torus拓扑"""
    topology = create_torus_topology()
    return topology.validate_torus_properties(size)
